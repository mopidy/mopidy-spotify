from __future__ import annotations

import copy
import itertools
import logging
import os
import re
import threading
import time
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum, auto, unique
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, ClassVar, Never, cast

import requests
from pydantic import BaseModel, ConfigDict, SecretStr, TypeAdapter, ValidationError

from mopidy_spotify import utils
from mopidy_spotify._ext import keyring
from mopidy_spotify.oauth import providers, state, store

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

    from mopidy.config import ProxyConfig
    from mopidy.types import Uri

logger = logging.getLogger(__name__)

type RefreshContext = tuple[
    store.Snapshot | None,
    providers.RefreshProvider,
]

BRIDGE_REFRESH_URL = "https://auth.mopidy.com/spotify/token"
SPOTIFY_REFRESH_URL = "https://accounts.spotify.com/api/token"


def _trace(*args: Any, **kwargs: Any) -> None:
    logger.log(utils.TRACE, *args, **kwargs)


class OAuthTokenRefreshError(Exception):
    def __init__(self, reason: str) -> None:
        message = f"OAuth token refresh failed: {reason}"
        super().__init__(message)


class OAuthPermanentRefreshError(OAuthTokenRefreshError):
    pass


class OAuthClientError(Exception):
    pass


class OAuthTokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    access_token: SecretStr
    token_type: str
    expires_in: int | float | None = None
    refresh_token: SecretStr | None = None
    scope: str | None = None


class OAuthErrorResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    error: str
    error_description: str | None = None


OAUTH_REFRESH_RESPONSE_ADAPTER = TypeAdapter(OAuthTokenResponse | OAuthErrorResponse)


def _parse_token_refresh_response(
    response: WebResponse,
) -> OAuthTokenResponse | OAuthErrorResponse:
    if "access_token" in response and "error" in response:
        msg = "invalid token response"
        raise OAuthTokenRefreshError(msg)

    try:
        parsed_response = OAUTH_REFRESH_RESPONSE_ADAPTER.validate_python(response)
    except ValidationError as exc:
        logger.debug(
            "Invalid OAuth token response: %s",
            exc.errors(include_url=False, include_context=False, include_input=False),
        )
        if "access_token" not in response and "error" not in response:
            msg = "missing access_token"
        else:
            msg = "invalid token response"
    else:
        if (
            isinstance(parsed_response, OAuthTokenResponse)
            and not parsed_response.access_token.get_secret_value()
        ):
            msg = "missing access_token"
            raise OAuthTokenRefreshError(msg)
        return parsed_response

    raise OAuthTokenRefreshError(msg)


class OAuthClient:
    def __init__(  # noqa: PLR0913
        self,
        *,
        base_url: str,
        refresh_url: str,
        client_id: str | None = None,
        client_secret: str | None = None,
        proxy_config: ProxyConfig | None = None,
        expiry_margin: int = 60,
        timeout: int = 10,
        retries: int = 3,
        retry_statuses: tuple[int, ...] = (500, 502, 503, 429),
    ) -> None:
        if client_id and client_secret:
            self._auth = (client_id, client_secret)
        else:
            self._auth = None
        self._access_token: SecretStr | None = None

        self._base_url = base_url
        self._refresh_url = refresh_url
        self._margin = expiry_margin
        self._expires = 0

        self._timeout = timeout
        self._number_of_retries = retries
        self._retry_statuses = retry_statuses
        self._backoff_factor = 0.5

        self._headers = {"Content-Type": "application/json"}
        self._session = utils.get_requests_session(proxy_config)
        # TODO: Move _cache_mutex to the object it actually protects.
        self._cache_mutex = threading.Lock()  # Protects get() cache param.
        self._refresh_mutex = threading.Lock()  # Protects _headers and _expires.

    def token(self) -> str | None:
        with self._refresh_mutex:
            try:
                if self._should_refresh_token():
                    self._refresh_token()
            except OAuthTokenRefreshError as e:
                logger.error(e)  # noqa: TRY400
                return None
            else:
                if self._access_token is None:
                    return None
                return self._access_token.get_secret_value()

    def get(
        self,
        path: str,
        cache: dict[str, WebResponse] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> WebResponse:
        params = kwargs.pop("params", None)
        path = self._normalise_query_string(path, params)

        _trace(f"Get '{path}'")

        expiry_strategy = kwargs.pop("expiry_strategy", None)
        if cache is not None and (cached_result := cache.get(path)) is not None:
            if cached_result.still_valid(expiry_strategy=expiry_strategy):
                return cached_result
            kwargs.setdefault("headers", {}).update(cached_result.etag_headers)

        # TODO: Factor this out once we add more methods.
        # TODO: Don't silently error out.
        with self._refresh_mutex:
            try:
                if self._should_refresh_token():
                    self._refresh_token()
            except OAuthTokenRefreshError as e:
                logger.error(e)  # noqa: TRY400
                return WebResponse(None, None)

        # Make sure our headers always override user supplied ones.
        kwargs.setdefault("headers", {}).update(self._headers)
        result = self._request_with_retries("GET", path, *args, **kwargs)

        if result is None or "error" in result:
            logger.error(
                "Spotify Web API request failed: "
                f"{result.get('error', 'Unknown') if result else 'Unknown'}"
            )
            return WebResponse(None, None)

        with self._cache_mutex:
            if cache is not None and self._should_cache_response(result):
                previous_result = cache.get(path)
                if previous_result and previous_result.updated(result):
                    result = previous_result
                cache[path] = result

        return result

    def _should_cache_response(self, response: WebResponse) -> bool:
        return response.status_ok

    def _should_refresh_token(self) -> bool:
        # TODO: Add jitter to margin?
        if not self._refresh_mutex.locked():
            msg = "Lock must be held before calling."
            raise OAuthTokenRefreshError(msg)
        return (
            "Authorization" not in self._headers and self._expires == 0
        ) or time.time() > self._expires - self._margin

    def _static_refresh_request(self) -> requests.Request:
        return requests.Request(
            "POST",
            self._refresh_url,
            auth=self._auth,
            data={"grant_type": "client_credentials"},
        )

    def _token_refresh_request(self) -> requests.Request:
        return self._static_refresh_request()

    def _is_permanent_error(self, error_code: str, *, context: Any = None) -> bool:
        _ = context
        return error_code == "invalid_grant"

    def _handle_permanent_error(
        self,
        error_code: str = "invalid_grant",
        error_description: str | None = None,
        *,
        context: Any = None,
    ) -> None:
        _ = context
        error = error_description or error_code
        raise OAuthPermanentRefreshError(error)

    def _handle_token_refresh_success(
        self,
        response: OAuthTokenResponse,
        *,
        context: Any = None,
    ) -> None:
        _ = response, context

    def _handle_token_refresh_error(
        self,
        response: OAuthErrorResponse,
        status_code: int | HTTPStatus | None,
        *,
        context: Any = None,
    ) -> Never:
        _ = status_code
        if self._is_permanent_error(response.error, context=context):
            self._handle_permanent_error(
                response.error,
                response.error_description,
                context=context,
            )
        msg = f"{response.error} {response.error_description or ''}"
        raise OAuthTokenRefreshError(msg)

    def _execute_token_refresh(
        self,
        request: requests.Request,
        *,
        context: Any = None,
    ) -> OAuthTokenResponse:
        logger.debug(f"Fetching OAuth token from {request.url}")
        if request.method is None or not isinstance(request.url, str):
            msg = "invalid token request"
            raise OAuthTokenRefreshError(msg)
        result = self._request_with_retries(
            request.method,
            request.url,
            auth=request.auth,
            data=request.data,
        )

        if result is None:
            msg = "Unknown error."
            raise OAuthTokenRefreshError(msg)

        response = _parse_token_refresh_response(result)
        if isinstance(response, OAuthErrorResponse):
            self._handle_token_refresh_error(
                response,
                result._status_code,
                context=context,
            )

        if not result.status_ok:
            msg = f"token endpoint returned HTTP {result._status_code}"
            raise OAuthTokenRefreshError(msg)

        if response.token_type != "Bearer":  # noqa: S105
            msg = f"wrong token_type: {response.token_type}"
            raise OAuthTokenRefreshError(msg)

        self._handle_token_refresh_success(response, context=context)

        self._access_token = response.access_token
        self._headers["Authorization"] = (
            f"Bearer {response.access_token.get_secret_value()}"
        )
        lifetime = float("Inf") if response.expires_in is None else response.expires_in
        self._expires = time.time() + lifetime

        if response.expires_in is not None:
            logger.debug(f"Token expires in {response.expires_in} seconds.")
        if response.scope:
            logger.debug(f"Token scopes: {response.scope}")

        return response

    def _refresh_token(self) -> None:
        if not self._refresh_mutex.locked():
            msg = "Lock must be held before calling."
            raise OAuthTokenRefreshError(msg)

        request = self._token_refresh_request()
        self._execute_token_refresh(request)

    def _request_with_retries(
        self,
        method: str,
        url: str,
        *args: Any,
        **kwargs: Any,
    ) -> WebResponse | None:
        prepared_request = self._session.prepare_request(
            requests.Request(method, self._prepare_url(url, *args), **kwargs)
        )

        try_until = time.time() + self._timeout

        status_code = None
        result = None
        backoff_time = 0

        for i in range(self._number_of_retries):
            remaining_timeout = max(try_until - time.time(), 1)

            # Give up if we don't have any timeout left after sleeping.
            if backoff_time > remaining_timeout:
                break
            if backoff_time > 0:
                time.sleep(backoff_time)

            try:
                response = self._session.send(
                    prepared_request, timeout=remaining_timeout
                )
            except requests.RequestException as e:
                logger.debug(f"Fetching {prepared_request.url} failed: {e}")
                status_code = None
                backoff_time = 0
                result = None
            else:
                status_code = response.status_code
                backoff_time = self._parse_retry_after(response)
                result = WebResponse.from_requests(prepared_request, response)

            if status_code and 400 <= status_code < 600:  # noqa: PLR2004
                logger.debug(f"Fetching {prepared_request.url} failed: {status_code}")

            # Filter out cases where we should not retry.
            if status_code and status_code not in self._retry_statuses:
                break

            # TODO: Provider might return invalid JSON for "OK" responses.
            # This should really not happen, so ignoring for the purpose of
            # retries. It would be easier if they correctly used 204, but
            # instead some endpoints return 200 with no content, or true/false.

            # Decide how long to sleep in the next iteration.
            backoff_time = backoff_time or (2**i * self._backoff_factor)
            logger.error(
                f"Retrying {prepared_request.url} in {backoff_time:.3f} seconds."
            )

        if status_code == HTTPStatus.UNAUTHORIZED:
            logger.error(
                "Authorization failed, not attempting Spotify API "
                "request. Please get new credentials from "
                "https://www.mopidy.com/authenticate and/or restart "
                "Mopidy to resolve this problem."
            )
        return result

    def _prepare_url(self, url: str, *args: Any, **kwargs: Any) -> str:
        # TODO: Move this out as a helper and unit-test it directly?
        b = urllib.parse.urlsplit(self._base_url)
        u = urllib.parse.urlsplit(url.format(*args))

        if u.scheme or u.netloc:
            scheme, netloc, path = u.scheme, u.netloc, u.path
            query = urllib.parse.parse_qsl(u.query, keep_blank_values=True)
        else:
            scheme, netloc = b.scheme, b.netloc
            path = os.path.normpath(os.path.join(b.path, u.path))  # noqa: PTH118
            query = urllib.parse.parse_qsl(b.query, keep_blank_values=True)
            query.extend(urllib.parse.parse_qsl(u.query, keep_blank_values=True))

        for key, value in kwargs.items():
            query.append((key, value))

        encoded_query = urllib.parse.urlencode(dict(query))
        return urllib.parse.urlunsplit((scheme, netloc, path, encoded_query, ""))

    def _normalise_query_string(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
    ) -> str:
        u = urllib.parse.urlsplit(url)
        scheme, netloc, path = u.scheme, u.netloc, u.path

        query = dict(urllib.parse.parse_qsl(u.query, keep_blank_values=True))
        if isinstance(params, dict):
            query.update(params)
        sorted_unique_query = sorted(query.items())
        encoded_query = urllib.parse.urlencode(sorted_unique_query)
        return urllib.parse.urlunsplit((scheme, netloc, path, encoded_query, ""))

    def _parse_retry_after(self, response: requests.Response) -> float:
        """Parse Retry-After header from response if it is set."""
        value = response.headers.get("Retry-After")

        if not value:
            seconds = 0
        elif re.match(r"^\s*[0-9]+\s*$", value):
            seconds = int(value)
        else:
            now = datetime.now(tz=UTC).replace(tzinfo=None)
            try:
                date_tuple = parsedate_to_datetime(value)
                seconds = (date_tuple - now).total_seconds()
            except ValueError:
                seconds = 0
        return max(0, seconds)


@unique
class ExpiryStrategy(StrEnum):
    FORCE_FRESH = "force-fresh"
    FORCE_EXPIRED = "force-expired"


class WebResponse(dict):
    def __init__(
        self,
        url: str | None,
        data: Mapping[str, Any] | None,
        *,
        expires: float = 0.0,
        etag: str | None = None,
        status_code: int = 400,
    ) -> None:
        self._from_cache = False
        self.url = url
        self._expires = expires
        self._etag = etag
        self._status_code = status_code
        super().__init__(data or {})
        _trace(f"New WebResponse {self}")

    @classmethod
    def from_requests(
        cls,
        request: requests.PreparedRequest,
        response: requests.Response,
    ) -> WebResponse:
        expires = cls._parse_cache_control(response)
        etag = cls._parse_etag(response)
        json = cls._decode(response)
        return cls(
            request.url,
            json,
            expires=expires,
            etag=etag,
            status_code=response.status_code,
        )

    @classmethod
    def from_batch(
        cls,
        batch_response: WebResponse,
        item_json: Mapping[str, Any] | None,
    ) -> WebResponse:
        return cls(
            batch_response.url,
            item_json,
            expires=batch_response._expires,
            etag=None,
            status_code=batch_response._status_code,
        )

    @staticmethod
    def _decode(response: requests.Response) -> Any:
        # Deal with 204 and other responses with empty body.
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as e:
            url = response.request.url
            logger.error(f"JSON decoding {url} failed: {e}")  # noqa: TRY400
            return None

    @staticmethod
    def _parse_cache_control(response: requests.Response) -> float:
        """Parse Cache-Control header from response if it is set."""
        value = response.headers.get("Cache-Control", "no-store").lower()

        if "no-store" in value:
            seconds = 0
        else:
            max_age = re.match(r".*max-age=\s*([0-9]+)\s*", value)
            seconds = 0 if not max_age else int(max_age.groups()[0])
        return time.time() + seconds

    @staticmethod
    def _parse_etag(response: requests.Response) -> str | None:
        """Parse ETag header from response if it is set."""
        value = response.headers.get("ETag")

        if value:
            # 'W/' (case-sensitive) indicates that a weak validator is used,
            # currently ignoring this.
            # Format is string of ASCII characters placed between double quotes
            # but can seemingly also include hyphen characters.
            etag = re.match(r'^(W/)?("[!#-~]+")$', value)
            if etag and len(etag.groups()) == 2:  # noqa: PLR2004
                return etag.groups()[1]

        return None

    def still_valid(self, *, expiry_strategy: ExpiryStrategy | None = None) -> bool:
        if expiry_strategy is None:
            if self._expires >= time.time():
                valid = True
                status = "fresh"
            else:
                valid = False
                status = "expired"
        else:
            valid = expiry_strategy is ExpiryStrategy.FORCE_FRESH
            status = expiry_strategy.value
        self._from_cache = valid
        _trace("Cached data %s for %s", status, self)
        return valid

    @property
    def status_unchanged(self) -> bool:
        return self._from_cache or self._status_code == HTTPStatus.NOT_MODIFIED

    @property
    def status_ok(self) -> bool:
        return self._status_code >= 200 and self._status_code < 400  # noqa: PLR2004

    @property
    def etag_headers(self) -> dict[str, str]:
        if self._etag is None:
            return {}
        return {"If-None-Match": self._etag}

    def updated(self, response: WebResponse) -> bool:
        self._from_cache = False
        if self._etag is None:
            return False
        if self.url != response.url:
            logger.error(f"ETag mismatch (different URI) for {self} {response}")
            return False
        if not response.status_ok:
            logger.debug(f"ETag mismatch (bad response) for {self} {response}")
            return False
        if response._status_code != HTTPStatus.NOT_MODIFIED:
            _trace(f"ETag mismatch for {self} {response}")
            return False

        _trace(f"ETag match for {self} {response}")
        self._expires = response._expires
        self._etag = response._etag
        self._status_code = response._status_code
        return True

    def __str__(self) -> str:
        return (
            f"URL: {self.url} "
            f"expires at: {datetime.fromtimestamp(self._expires, tz=UTC)} "
            f"[ETag: {self._etag}]"
        )

    def __repr__(self) -> str:
        return f"WebResponse({self})"

    def increase_expiry(self, delta_seconds: float) -> None:
        if self.status_ok and not self._from_cache:
            self._expires += delta_seconds


@unique
class LinkType(StrEnum):
    TRACK = auto()
    ALBUM = auto()
    ARTIST = auto()
    PLAYLIST = auto()
    YOUR = auto()


@dataclass
class WebLink:
    uri: Uri
    type: LinkType
    id: str | None = None
    owner: str | None = None

    @classmethod
    def from_uri(cls, uri: Uri) -> WebLink:
        parsed_uri = urllib.parse.urlparse(uri)

        schemes = ("http", "https")
        netlocs = ("open.spotify.com", "play.spotify.com")

        if parsed_uri.scheme == "spotify":
            parts = parsed_uri.path.split(":")
        elif parsed_uri.scheme in schemes and parsed_uri.netloc in netlocs:
            parts = parsed_uri.path[1:].split("/")
        else:
            parts = []

        # Strip out empty parts to ensure we are strict about URI parsing.
        parts = [p for p in parts if p.strip()]

        match parts:
            case [type, id] if type in ("track", "album", "artist", "playlist"):
                return cls(uri, LinkType(type), id, None)
            case ["your", _]:
                return cls(uri, LinkType.YOUR)
            case ["user", owner, "starred"]:
                if parsed_uri.scheme == "spotify":
                    return cls(uri, LinkType.PLAYLIST, None, owner)
            case ["playlist", owner, id]:
                return cls(uri, LinkType.PLAYLIST, id, owner)
            case ["user", owner, "playlist", id]:
                return cls(uri, LinkType.PLAYLIST, id, owner)

        msg = f"Could not parse {uri!r} as a Spotify URI"
        raise ValueError(msg)

    def __hash__(self) -> int:
        return hash(self.uri)


class WebError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


API_MAX_IDS_PER_REQUEST: dict[LinkType, int] = {
    LinkType.TRACK: 50,  # API limit is actually 100. Any reason not to use that?
    LinkType.ARTIST: 50,
    LinkType.ALBUM: 20,
}


class SpotifyOAuthClient(OAuthClient):
    TRACK_FIELDS: ClassVar[str] = (
        "next,items(track(type,uri,name,duration_ms,disc_number,track_number,"
        "artists,album,is_playable,linked_from.uri))"
    )
    PLAYLIST_FIELDS: ClassVar[str] = (
        f"name,owner(id),type,uri,snapshot_id,tracks({TRACK_FIELDS}),"
    )
    DEFAULT_EXTRA_EXPIRY: ClassVar[int] = 10

    def __init__(
        self,
        *,
        client_id: str | None,
        client_secret: str | None,
        auth_state_path: Path | None = None,
        proxy_config: ProxyConfig | None = None,
    ) -> None:
        if auth_state_path is None:
            self._auth_state_store = None
        else:
            self._auth_state_store = store.Store(auth_state_path)
        self._refresh_providers: tuple[
            providers.RefreshProvider,
            ...,
        ] = (
            providers.PkceRefreshProvider(),
            providers.BridgeRefreshProvider(
                client_id=client_id,
                client_secret=client_secret,
            ),
        )
        super().__init__(
            base_url="https://api.spotify.com/v1",
            refresh_url=BRIDGE_REFRESH_URL,
            client_id=client_id,
            client_secret=client_secret,
            proxy_config=proxy_config,
        )
        self.user_id: str | None = None
        self._cache: dict[str, WebResponse] = {}
        self._extra_expiry = self.DEFAULT_EXTRA_EXPIRY

    def _load_auth_state(self) -> store.Snapshot | None:
        if self._auth_state_store is None:
            return None

        try:
            return self._auth_state_store.load()
        except (
            store.InvalidManifestError,
            store.Error,
            keyring.Error,
        ) as exc:
            msg = f"{exc}. Run `mopidy spotify auth web` to replace it."
            raise OAuthPermanentRefreshError(msg) from exc

    def _token_refresh_request_for_state(
        self,
        snapshot: store.Snapshot | None,
    ) -> tuple[requests.Request, providers.RefreshProvider]:
        auth_state = snapshot.state if snapshot is not None else None
        if isinstance(auth_state, state.PermanentError) and auth_state.mode == "pkce":
            detail = auth_state.error_description or auth_state.error_code
            raise OAuthPermanentRefreshError(detail)

        for provider in self._refresh_providers:
            request = provider.request_for(auth_state)
            if request is not None:
                return request, provider

        msg = "No refresh provider available."
        raise OAuthTokenRefreshError(msg)

    def _token_refresh_request(self) -> requests.Request:
        snapshot = self._load_auth_state()
        request, _ = self._token_refresh_request_for_state(snapshot)
        return request

    def _save_auth_state(
        self,
        expected: store.Snapshot | None,
        next_state: state.State,
    ) -> None:
        if self._auth_state_store is None:
            return
        try:
            saved = self._auth_state_store.compare_and_set(expected, next_state)
        except (
            store.InvalidManifestError,
            store.Error,
            keyring.Error,
        ) as exc:
            msg = "could not persist Spotify authorization state"
            raise OAuthTokenRefreshError(msg) from exc
        if not saved:
            msg = "Spotify authorization changed during token refresh"
            raise OAuthTokenRefreshError(msg)

    def _refresh_token(self) -> None:
        if not self._refresh_mutex.locked():
            msg = "Lock must be held before calling."
            raise OAuthTokenRefreshError(msg)

        snapshot = self._load_auth_state()
        request, provider = self._token_refresh_request_for_state(snapshot)
        self._execute_token_refresh(request, context=(snapshot, provider))

    def _handle_token_refresh_success(
        self,
        response: OAuthTokenResponse,
        *,
        context: Any = None,
    ) -> None:
        refresh_context = cast("RefreshContext", context)
        snapshot, provider = refresh_context
        auth_state = snapshot.state if snapshot is not None else None
        self._save_auth_state(
            snapshot,
            provider.state_after_success(response, auth_state),
        )

    def _handle_token_refresh_error(
        self,
        response: OAuthErrorResponse,
        status_code: int | HTTPStatus | None,
        *,
        context: Any = None,
    ) -> Never:
        refresh_context = cast("RefreshContext", context)
        snapshot, provider = refresh_context
        auth_state = snapshot.state if snapshot is not None else None
        next_state = provider.state_after_error(response, auth_state, status_code)
        self._save_auth_state(snapshot, next_state)
        if next_state.mode == "pkce":
            detail = (
                "Spotify refresh token is no longer valid. "
                "Run `mopidy spotify auth web` to reauthorize."
            )
        else:
            detail = response.error_description or response.error
        raise OAuthPermanentRefreshError(detail)

    def get_one(self, path: str, *args: Any, **kwargs: Any) -> WebResponse:
        _trace(f"Fetching page {path!r}")
        result = self.get(path, self._cache, *args, **kwargs)
        result.increase_expiry(self._extra_expiry)
        return result

    def get_all(
        self, path: str | None, *args: Any, **kwargs: Any
    ) -> Iterator[WebResponse]:
        while path is not None:
            result = self.get_one(path, *args, **kwargs)
            path = result.get("next")
            yield result

    def login(self) -> bool:
        self.user_id = self.get("me").get("id")
        if self.user_id is None:
            logger.error("Failed to load Spotify user profile")
            return False
        logger.info(f"Logged into Spotify Web API as {self.user_id}")
        return True

    @property
    def logged_in(self) -> bool:
        return self.user_id is not None

    def get_user_playlists(
        self, *, refresh: bool = False
    ) -> Iterator[Mapping[str, Any]]:
        expiry_strategy = ExpiryStrategy.FORCE_EXPIRED if refresh else None
        pages = self.get_all(
            f"users/{self.user_id}/playlists",
            params={"limit": 50},
            expiry_strategy=expiry_strategy,
        )
        for page in pages:
            yield from page.get("items", [])

    def _with_all_tracks(
        self,
        obj: WebResponse,
        params: Mapping[str, Any] | None = None,
    ) -> WebResponse | dict[str, Any]:
        if params is None:
            params = {}
        tracks_path = obj.get("tracks", {}).get("next")
        track_pages = self.get_all(
            tracks_path,
            params=params,
            expiry_strategy=(
                ExpiryStrategy.FORCE_FRESH if obj.status_unchanged else None
            ),
        )

        more_tracks = []
        for page in track_pages:
            if "items" not in page:
                return {}  # Return nothing on error, or what we have so far?
            more_tracks += page["items"]

        if more_tracks:
            # Take a copy to avoid changing the cached response.
            obj = copy.deepcopy(obj)
            obj.setdefault("tracks", {}).setdefault("items", [])
            obj["tracks"]["items"] += more_tracks

        return obj

    def get_playlist(self, uri: Uri) -> Mapping[str, Any]:
        try:
            parsed = WebLink.from_uri(uri)
            if parsed.type != LinkType.PLAYLIST:
                msg = f"Could not parse {uri!r} as a Spotify playlist URI"
                raise ValueError(msg)  # noqa: TRY301
        except ValueError as exc:
            logger.error(exc)  # noqa: TRY400
            return {}

        playlist = self.get_one(
            f"playlists/{parsed.id}",
            params={"fields": self.PLAYLIST_FIELDS, "market": "from_token"},
        )
        return self._with_all_tracks(playlist, {"fields": self.TRACK_FIELDS})

    def get_batch(
        self,
        link_type: LinkType,
        links: list[WebLink],
    ) -> Iterator[tuple[WebLink, WebResponse]]:
        if not links:
            return
        if link_type not in API_MAX_IDS_PER_REQUEST:
            logger.warning(f"Cannot handle batched {link_type}s")
            return

        links = list(dict.fromkeys(links))  # Remove duplicates and maintain order
        for batch in itertools.batched(
            links, API_MAX_IDS_PER_REQUEST[link_type], strict=False
        ):
            ids = [u.id for u in batch if u.id is not None]
            ids_to_links = {u.id: u for u in batch}
            data = self.get_one(
                f"{link_type}s", params={"ids": ",".join(ids), "market": "from_token"}
            )
            for item in data.get(f"{link_type}s") or []:
                if not item:
                    continue

                # For track re-linking.
                if "linked_from" in item:
                    item_id = item["linked_from"].get("id")
                else:
                    item_id = item.get("id")
                if link := ids_to_links.get(item_id):
                    yield link, WebResponse.from_batch(data, item)
                else:
                    logger.warning(f"Invalid batch item: {item}")

    def get_albums(self, album_links: list[WebLink]) -> Iterator[Mapping[str, Any]]:
        result = {}
        for link_type, link_group in utils.group_by_type(album_links):
            if link_type != LinkType.ALBUM:
                logger.error("Expecting Spotify album URIs")
                continue
            result.update(self.get_batch(link_type, list(link_group)))

        for link in album_links:
            if album := result.get(link):
                yield self._with_all_tracks(album)

    def get_artist_albums(
        self, web_link: WebLink, *, all_tracks: bool = True
    ) -> Iterator[Mapping[str, Any]]:
        if web_link.type != LinkType.ARTIST:
            logger.error("Expecting Spotify artist URI")
            return []

        pages = self.get_all(
            f"artists/{web_link.id}/albums",
            params={"market": "from_token", "include_groups": "single,album"},
        )
        album_links = []
        for page in pages:
            for album in page.get("items") or []:
                if all_tracks:
                    try:
                        album_links.append(WebLink.from_uri(album.get("uri")))
                    except ValueError as exc:
                        logger.error(exc)  # noqa: TRY400
                        continue
                else:
                    yield album
        if all_tracks:
            yield from self.get_albums(album_links)

    def get_artist_top_tracks(self, web_link: WebLink) -> list[Mapping[str, Any]]:
        if web_link.type != LinkType.ARTIST:
            logger.error("Expecting Spotify artist URI")
            return []

        return (
            self.get_one(
                f"artists/{web_link.id}/top-tracks",
                params={"market": "from_token"},
            ).get("tracks")
            or []
        )

    def get_track(self, web_link: WebLink) -> Mapping[str, Any]:
        if web_link.type != LinkType.TRACK:
            logger.error("Expecting Spotify track URI")
            return {}

        return self.get_one(f"tracks/{web_link.id}", params={"market": "from_token"})
