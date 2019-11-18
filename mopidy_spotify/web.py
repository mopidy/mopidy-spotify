import email
import logging
import os
import re
import time
import urllib.parse
from datetime import datetime

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
    def __init__(
        self,
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

    def get(self, path, cache=None, *args, **kwargs):
        if self._authorization_failed:
            logger.debug("Blocking request as previous authorization failed.")
            return {}

        params = kwargs.pop("params", None)
        path = self._normalise_query_string(path, params)

        _trace(f"Get '{path}'")

        if cache is not None and path in cache:
            cached_result = cache.get(path)
            if not cached_result.expired:
                return cached_result
            kwargs.setdefault("headers", {}).update(cached_result.etag_headers)

        # TODO: Factor this out once we add more methods.
        # TODO: Don't silently error out.
        try:
            if self._should_refresh_token():
                self._refresh_token()
        except OAuthTokenRefreshError as e:
            logger.error(e)
            return {}

        # Make sure our headers always override user supplied ones.
        kwargs.setdefault("headers", {}).update(self._headers)
        result = self._request_with_retries("GET", path, *args, **kwargs)

        if result is None or "error" in result:
            return {}

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
        return not self._auth or time.time() > self._expires - self._margin

    def _refresh_token(self):
        logger.debug(f"Fetching OAuth token from {self._refresh_url}")

        data = {"grant_type": "client_credentials"}
        result = self._request_with_retries(
            "POST", self._refresh_url, auth=self._auth, data=data
        )

        if result is None:
            raise OAuthTokenRefreshError("Unknown error.")
        elif result.get("error"):
            raise OAuthTokenRefreshError(
                f"{result['error']} {result.get('error_description', '')}"
            )
        elif not result.get("access_token"):
            raise OAuthTokenRefreshError("missing access_token")
        elif result.get("token_type") != "Bearer":
            raise OAuthTokenRefreshError(
                f"wrong token_type: {result.get('token_type')}"
            )

        self._headers["Authorization"] = f"Bearer {result['access_token']}"
        self._expires = time.time() + result.get("expires_in", float("Inf"))

        if result.get("expires_in"):
            logger.debug(f"Token expires in {result['expires_in']} seconds.",)
        if result.get("scope"):
            logger.debug(f"Token scopes: {result['scope']}")

    def _request_with_retries(self, method, url, *args, **kwargs):
        prepared_request = self._session.prepare_request(
            requests.Request(method, self._prepare_url(url, *args), **kwargs)
        )

        try_until = time.time() + self._timeout

        result = None
        backoff_time = 0

        for i in range(self._number_of_retries):
            remaining_timeout = max(try_until - time.time(), 1)

            # Give up if we don't have any timeout left after sleeping.
            if backoff_time > remaining_timeout:
                break
            elif backoff_time > 0:
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

            if status_code >= 400 and status_code < 600:
                logger.debug(
                    f"Fetching {prepared_request.url} failed: {status_code}"
                )

            # Filter out cases where we should not retry.
            if status_code and status_code not in self._retry_statuses:
                break

            # TODO: Provider might return invalid JSON for "OK" responses.
            # This should really not happen, so ignoring for the purpose of
            # retries. It would be easier if they correctly used 204, but
            # instead some endpoints return 200 with no content, or true/false.

            # Decide how long to sleep in the next iteration.
            backoff_time = backoff_time or (2 ** i * self._backoff_factor)
            logger.debug(
                f"Retrying {prepared_request.url} in {backoff_time:.3f} "
                "seconds."
            )

        if status_code == 401:
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
            path = os.path.normpath(os.path.join(b.path, u.path))
            query = urllib.parse.parse_qsl(b.query, keep_blank_values=True)
            query.extend(
                urllib.parse.parse_qsl(u.query, keep_blank_values=True)
            )

        for key, value in kwargs.items():
            query.append((key, value))

        encoded_query = urllib.parse.urlencode(dict(query))
        return urllib.parse.urlunsplit(
            (scheme, netloc, path, encoded_query, "")
        )

    def _normalise_query_string(self, url, params=None):
        u = urllib.parse.urlsplit(url)
        scheme, netloc, path = u.scheme, u.netloc, u.path

        query = dict(urllib.parse.parse_qsl(u.query, keep_blank_values=True))
        if isinstance(params, dict):
            query.update(params)
        sorted_unique_query = sorted(query.items())
        encoded_query = urllib.parse.urlencode(sorted_unique_query)
        return urllib.parse.urlunsplit(
            (scheme, netloc, path, encoded_query, "")
        )

    def _parse_retry_after(self, response):
        """Parse Retry-After header from response if it is set."""
        value = response.headers.get("Retry-After")

        if not value:
            seconds = 0
        elif re.match(r"^\s*[0-9]+\s*$", value):
            seconds = int(value)
        else:
            date_tuple = email.utils.parsedate(value)
            if date_tuple is None:
                seconds = 0
            else:
                seconds = time.mktime(date_tuple) - time.time()
        return max(0, seconds)


class WebResponse(dict):
    def __init__(self, url, data, expires=0.0, etag=None, status_code=400):
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
        return cls(request.url, json, expires, etag, response.status_code)

    @staticmethod
    def _decode(response):
        # Deal with 204 and other responses with empty body.
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as e:
            url = response.request.url
            logger.error(f"JSON decoding {url} failed: {e}")
            return None

    @staticmethod
    def _parse_cache_control(response):
        """Parse Cache-Control header from response if it is set."""
        value = response.headers.get("Cache-Control", "no-store").lower()

        if "no-store" in value:
            seconds = 0
        else:
            max_age = re.match(r".*max-age=\s*([0-9]+)\s*", value)
            if not max_age:
                seconds = 0
            else:
                seconds = int(max_age.groups()[0])
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
            if etag and len(etag.groups()) == 2:
                return etag.groups()[1]

    @property
    def expired(self):
        status_str = {True: "expired", False: "fresh"}
        result = self._expires < time.time()
        _trace(f"Cached data {status_str[result]} for {self}")
        return result

    @property
    def status_ok(self):
        return self._status_code >= 200 and self._status_code < 400

    @property
    def etag_headers(self):
        if self._etag is not None:
            return {"If-None-Match": self._etag}
        else:
            return {}

    def updated(self, response):
        if self._etag is None:
            return False
        elif self.url != response.url:
            logger.error(f"ETag mismatch (different URI) for {self} {response}")
            return False
        elif not response.status_ok:
            logger.debug(f"ETag mismatch (bad response) for {self} {response}")
            return False
        elif response._status_code != 304:
            _trace(f"ETag mismatch for {self} {response}")
            return False

        _trace(f"ETag match for {self} {response}")
        self._expires = response._expires
        self._etag = response._etag
        return True

    def __str__(self):
        return (
            f"URL: {self.url} ETag: {self._etag} "
            f"Expires: {datetime.fromtimestamp(self._expires)}"
        )
