import copy
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

import requests

from mopidy_spotify import utils

logger = logging.getLogger(__name__)


def _trace(*args, **kwargs):
    logger.log(utils.TRACE, *args, **kwargs)


class OAuthTokenRefreshError(Exception):
    def __init__(self, reason):
        message = f"OAuth token refresh failed: {reason}"
        super().__init__(message)


class OAuthClientError(Exception):
    pass


class OAuthClient:
    def __init__(  # noqa: PLR0913
        self,
        *,
        base_url,
        refresh_url,
        client_id=None,
        client_secret=None,
        proxy_config=None,
        expiry_margin=60,
        timeout=10,
        retries=3,
        retry_statuses=(500, 502, 503, 429),
    ):
        if client_id and client_secret:
            self._auth = (client_id, client_secret)
        else:
            self._auth = None
        self._access_token = None

        self._base_url = base_url
        self._refresh_url = refresh_url

        self._margin = expiry_margin
        self._expires = 0
        self._authorization_failed = False

        self._timeout = timeout
        self._number_of_retries = retries
        self._retry_statuses = retry_statuses
        self._backoff_factor = 0.5

        self._headers = {"Content-Type": "application/json"}
        self._session = utils.get_requests_session(proxy_config or {})
        # TODO: Move _cache_mutex to the object it actually protects.
        self._cache_mutex = threading.Lock()  # Protects get() cache param.
        self._refresh_mutex = threading.Lock()  # Protects _headers and _expires.

    def token(self):
        with self._refresh_mutex:
            try:
                if self._should_refresh_token():
                    self._refresh_token()
            except OAuthTokenRefreshError as e:
                logger.error(e)  # noqa: TRY400
                return None
            else:
                return self._access_token

    def get(self, path, cache=None, *args, **kwargs):
        if self._authorization_failed:
            logger.debug("Blocking request as previous authorization failed.")
            return WebResponse(None, None)

        params = kwargs.pop("params", None)
        path = self._normalise_query_string(path, params)

        _trace(f"Get '{path}'")

        expiry_strategy = kwargs.pop("expiry_strategy", None)
        if cache is not None and path in cache:
            cached_result = cache.get(path)
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
            if self._should_cache_response(cache, result):
                previous_result = cache.get(path)
                if previous_result and previous_result.updated(result):
                    result = previous_result
                cache[path] = result

        return result

    def _should_cache_response(self, cache, response):
        return cache is not None and response.status_ok

    def _should_refresh_token(self):
        # TODO: Add jitter to margin?
        if not self._refresh_mutex.locked():
            msg = "Lock must be held before calling."
            raise OAuthTokenRefreshError(msg)
        return not self._auth or time.time() > self._expires - self._margin

    def _refresh_token(self):
        logger.debug(f"Fetching OAuth token from {self._refresh_url}")

        if not self._refresh_mutex.locked():
            msg = "Lock must be held before calling."
            raise OAuthTokenRefreshError(msg)

        data = {"grant_type": "client_credentials"}
        result = self._request_with_retries(
            "POST", self._refresh_url, auth=self._auth, data=data
        )

        if result is None:
            msg = "Unknown error."
            raise OAuthTokenRefreshError(msg)
        if result.get("error"):
            msg = f"{result['error']} {result.get('error_description', '')}"
            raise OAuthTokenRefreshError(msg)
        if not result.get("access_token"):
            msg = "missing access_token"
            raise OAuthTokenRefreshError(msg)
        if result.get("token_type") != "Bearer":
            msg = f"wrong token_type: {result.get('token_type')}"
            raise OAuthTokenRefreshError(msg)

        self._access_token = result["access_token"]
        self._headers["Authorization"] = f"Bearer {self._access_token}"
        self._expires = time.time() + result.get("expires_in", float("Inf"))

        if result.get("expires_in"):
            logger.debug(
                f"Token expires in {result['expires_in']} seconds.",
            )
        if result.get("scope"):
            logger.debug(f"Token scopes: {result['scope']}")

    def _request_with_retries(self, method, url, *args, **kwargs):
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
            self._authorization_failed = True
            logger.error(
                "Authorization failed, not attempting Spotify API "
                "request. Please get new credentials from "
                "https://www.mopidy.com/authenticate and/or restart "
                "Mopidy to resolve this problem."
            )
        return result

    def _prepare_url(self, url, *args, **kwargs):
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

    def _normalise_query_string(self, url, params=None):
        u = urllib.parse.urlsplit(url)
        scheme, netloc, path = u.scheme, u.netloc, u.path

        query = dict(urllib.parse.parse_qsl(u.query, keep_blank_values=True))
        if isinstance(params, dict):
            query.update(params)
        sorted_unique_query = sorted(query.items())
        encoded_query = urllib.parse.urlencode(sorted_unique_query)
        return urllib.parse.urlunsplit((scheme, netloc, path, encoded_query, ""))

    def _parse_retry_after(self, response):
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
        url,
        data,
        *,
        expires=0.0,
        etag=None,
        status_code=400,
    ):
        self._from_cache = False
        self.url = url
        self._expires = expires
        self._etag = etag
        self._status_code = status_code
        super().__init__(data or {})
        _trace(f"New WebResponse {self}")

    @classmethod
    def from_requests(cls, request, response):
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
    def from_batch(cls, batch_response, item_json):
        return cls(
            batch_response.url,
            item_json,
            expires=batch_response._expires,
            etag=None,
            status_code=batch_response._status_code,
        )

    @staticmethod
    def _decode(response):
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
    def _parse_cache_control(response):
        """Parse Cache-Control header from response if it is set."""
        value = response.headers.get("Cache-Control", "no-store").lower()

        if "no-store" in value:
            seconds = 0
        else:
            max_age = re.match(r".*max-age=\s*([0-9]+)\s*", value)
            seconds = 0 if not max_age else int(max_age.groups()[0])
        return time.time() + seconds

    @staticmethod
    def _parse_etag(response):
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

    def still_valid(self, *, expiry_strategy=None):
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
    def status_unchanged(self):
        return self._from_cache or self._status_code == HTTPStatus.NOT_MODIFIED

    @property
    def status_ok(self):
        return self._status_code >= 200 and self._status_code < 400  # noqa: PLR2004

    @property
    def etag_headers(self):
        if self._etag is None:
            return {}
        return {"If-None-Match": self._etag}

    def updated(self, response):
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

    def __str__(self):
        return (
            f"URL: {self.url} "
            f"expires at: {datetime.fromtimestamp(self._expires, tz=UTC)} "
            f"[ETag: {self._etag}]"
        )

    def increase_expiry(self, delta_seconds):
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
    uri: str
    type: LinkType
    id: str | None = None
    owner: str | None = None

    @classmethod
    def from_uri(cls, uri):
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

    def __hash__(self):
        return hash(self.uri)


class WebError(Exception):
    def __init__(self, message):
        super().__init__(message)


API_MAX_IDS_PER_REQUEST = {
    LinkType.TRACK: 50,  # API limit is actually 100. Any reason not to use that?
    LinkType.ARTIST: 50,
    LinkType.ALBUM: 20,
}


class SpotifyOAuthClient(OAuthClient):
    TRACK_FIELDS = (
        "next,items(track(type,uri,name,duration_ms,disc_number,track_number,"
        "artists,album,is_playable,linked_from.uri))"
    )
    PLAYLIST_FIELDS = f"name,owner(id),type,uri,snapshot_id,tracks({TRACK_FIELDS}),"
    DEFAULT_EXTRA_EXPIRY = 10

    def __init__(self, *, refresh_url, client_id, client_secret, proxy_config):
        super().__init__(
            base_url="https://api.spotify.com/v1",
            refresh_url=refresh_url,
            client_id=client_id,
            client_secret=client_secret,
            proxy_config=proxy_config,
        )
        self.user_id = None
        self._cache = {}
        self._extra_expiry = self.DEFAULT_EXTRA_EXPIRY

    def get_one(self, path, *args, **kwargs):
        _trace(f"Fetching page {path!r}")
        result = self.get(path, self._cache, *args, **kwargs)
        result.increase_expiry(self._extra_expiry)
        return result

    def get_all(self, path, *args, **kwargs):
        while path is not None:
            result = self.get_one(path, *args, **kwargs)
            path = result.get("next")
            yield result

    def login(self):
        self.user_id = self.get("me").get("id")
        if self.user_id is None:
            logger.error("Failed to load Spotify user profile")
            return False
        logger.info(f"Logged into Spotify Web API as {self.user_id}")
        return True

    @property
    def logged_in(self):
        return self.user_id is not None

    def get_user_playlists(self, *, refresh=False):
        expiry_strategy = ExpiryStrategy.FORCE_EXPIRED if refresh else None
        pages = self.get_all(
            f"users/{self.user_id}/playlists",
            params={"limit": 50},
            expiry_strategy=expiry_strategy,
        )
        for page in pages:
            yield from page.get("items", [])

    def _with_all_tracks(self, obj, params=None):
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

    def get_playlist(self, uri):
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

    def get_batch(self, link_type, links):
        result = []
        if not links:
            return result
        if link_type not in API_MAX_IDS_PER_REQUEST:
            logger.warning(f"Cannot handle batched {link_type}s")
            return result

        links = list(dict.fromkeys(links))  # Remove duplicates and maintain order
        for batch in utils.batched(links, API_MAX_IDS_PER_REQUEST[link_type]):
            ids = [u.id for u in batch]
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

    def get_albums(self, album_links):
        result = {}
        for link_type, link_group in utils.group_by_type(album_links):
            if link_type != LinkType.ALBUM:
                logger.error("Expecting Spotify album URIs")
                continue
            result.update(self.get_batch(link_type, link_group))

        for link in album_links:
            if album := result.get(link):
                yield self._with_all_tracks(album)

    def get_artist_albums(self, web_link, *, all_tracks=True):
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

    def get_artist_top_tracks(self, web_link):
        if web_link.type != LinkType.ARTIST:
            logger.error("Expecting Spotify artist URI")
            return []

        return self.get_one(
            f"artists/{web_link.id}/top-tracks",
            params={"market": "from_token"},
        ).get("tracks")

    def get_track(self, web_link):
        if web_link.type != LinkType.TRACK:
            logger.error("Expecting Spotify track URI")
            return {}

        return self.get_one(f"tracks/{web_link.id}", params={"market": "from_token"})
