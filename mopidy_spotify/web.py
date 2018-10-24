from __future__ import unicode_literals

import collections
import copy
import email
import logging
import os
import re
import time
import urllib
import urlparse
from datetime import datetime

import requests

from mopidy_spotify import utils

logger = logging.getLogger(__name__)


def _trace(*args, **kwargs):
    logger.log(utils.TRACE, *args, **kwargs)


class OAuthTokenRefreshError(Exception):
    def __init__(self, reason):
        message = 'OAuth token refresh failed: %s' % reason
        super(OAuthTokenRefreshError, self).__init__(message)


class OAuthClientError(Exception):
    pass


class OAuthClient(object):

    def __init__(self, base_url, refresh_url, client_id=None,
                 client_secret=None, proxy_config=None, expiry_margin=60,
                 timeout=10, retries=3, retry_statuses=(500, 502, 503, 429)):

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

        self._headers = {'Content-Type': 'application/json'}
        self._session = utils.get_requests_session(proxy_config or {})

    def get(self, path, cache=None, *args, **kwargs):
        if self._authorization_failed:
            logger.debug('Blocking request as previous authorization failed.')
            return {}

        params = kwargs.pop('params', None)
        path = self._normalise_query_string(path, params)

        _trace('Get "%s"', path)

        if cache is not None and path in cache:
            cached_result = cache.get(path)
            if not cached_result.expired:
                return cached_result
            kwargs.setdefault('headers', {}).update(cached_result.etag_headers)

        # TODO: Factor this out once we add more methods.
        # TODO: Don't silently error out.
        try:
            if self._should_refresh_token():
                self._refresh_token()
        except OAuthTokenRefreshError as e:
            logger.error(e)
            return {}

        # Make sure our headers always override user supplied ones.
        kwargs.setdefault('headers', {}).update(self._headers)
        result = self._request_with_retries('GET', path, *args, **kwargs)

        if result is None or 'error' in result:
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
        logger.debug('Fetching OAuth token from %s', self._refresh_url)

        data = {'grant_type': 'client_credentials'}
        result = self._request_with_retries(
            'POST', self._refresh_url, auth=self._auth, data=data)

        if result is None:
            raise OAuthTokenRefreshError('Unknown error.')
        elif result.get('error'):
            raise OAuthTokenRefreshError('%s %s' % (
                result['error'], result.get('error_description', '')))
        elif not result.get('access_token'):
            raise OAuthTokenRefreshError('missing access_token')
        elif result.get('token_type') != 'Bearer':
            raise OAuthTokenRefreshError('wrong token_type: %s' %
                                         result.get('token_type'))

        self._headers['Authorization'] = 'Bearer %s' % result['access_token']
        self._expires = time.time() + result.get('expires_in', float('Inf'))

        if result.get('expires_in'):
            logger.debug('Token expires in %s seconds.', result['expires_in'])
        if result.get('scope'):
            logger.debug('Token scopes: %s', result['scope'])

    def _request_with_retries(self, method, url, *args, **kwargs):
        prepared_request = self._session.prepare_request(
            requests.Request(method, self._prepare_url(url, *args), **kwargs))

        try_until = time.time() + self._timeout

        result = None
        backoff_time = None

        for i in range(self._number_of_retries):
            remaining_timeout = max(try_until - time.time(), 1)

            # Give up if we don't have any timeout left after sleeping.
            if backoff_time > remaining_timeout:
                break
            elif backoff_time > 0:
                time.sleep(backoff_time)

            try:
                response = self._session.send(
                    prepared_request, timeout=remaining_timeout)
            except requests.RequestException as e:
                logger.debug('Fetching %s failed: %s', prepared_request.url, e)
                status_code = None
                backoff_time = None
                result = None
            else:
                status_code = response.status_code
                backoff_time = self._parse_retry_after(response)
                result = WebResponse.from_requests(prepared_request, response)

            if status_code >= 400 and status_code < 600:
                logger.debug('Fetching %s failed: %s',
                             prepared_request.url, status_code)

            # Filter out cases where we should not retry.
            if status_code and status_code not in self._retry_statuses:
                break

            # TODO: Provider might return invalid JSON for "OK" responses.
            # This should really not happen, so ignoring for the purpose of
            # retries. It would be easier if they correctly used 204, but
            # instead some endpoints return 200 with no content, or true/false.

            # Decide how long to sleep in the next iteration.
            backoff_time = backoff_time or (2**i * self._backoff_factor)
            logger.debug('Retrying %s in %.3f seconds.',
                         prepared_request.url, backoff_time)

        if status_code == 401:
            self._authorization_failed = True
            logger.error('Authorization failed, not attempting Spotify API '
                         'request. Please get new credentials from '
                         'https://www.mopidy.com/authenticate and/or restart '
                         'Mopidy to resolve this problem.')
        return result

    def _prepare_url(self, url, *args, **kwargs):
        # TODO: Move this out as a helper and unit-test it directly?
        b = urlparse.urlsplit(self._base_url)
        u = urlparse.urlsplit(url.format(*args))

        if u.scheme or u.netloc:
            scheme, netloc, path = u.scheme, u.netloc, u.path
            query = urlparse.parse_qsl(u.query, keep_blank_values=True)
        else:
            scheme, netloc = b.scheme, b.netloc
            path = os.path.normpath(os.path.join(b.path, u.path))
            query = urlparse.parse_qsl(b.query, keep_blank_values=True)
            query.extend(urlparse.parse_qsl(u.query, keep_blank_values=True))

        for key, value in kwargs.items():
            if isinstance(value, unicode):
                value = value.encode('utf-8')
            query.append((key, value))

        encoded_query = urllib.urlencode(dict(query))
        return urlparse.urlunsplit((scheme, netloc, path, encoded_query, ''))

    def _normalise_query_string(self, url, params=None):
        u = urlparse.urlsplit(url)
        scheme, netloc, path = u.scheme, u.netloc, u.path

        query = dict(urlparse.parse_qsl(u.query, keep_blank_values=True))
        if isinstance(params, dict):
            query.update(params)
        sorted_unique_query = sorted(query.items())
        encoded_query = urllib.urlencode(sorted_unique_query)
        return urlparse.urlunsplit((scheme, netloc, path, encoded_query, ''))

    def _parse_retry_after(self, response):
        """Parse Retry-After header from response if it is set."""
        value = response.headers.get('Retry-After')

        if not value:
            seconds = 0
        elif re.match(r'^\s*[0-9]+\s*$', value):
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
        super(WebResponse, self).__init__(data or {})
        _trace('New WebResponse %s', self)

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
            logger.error('JSON decoding %s failed: %s', url, e)
            return None

    @staticmethod
    def _parse_cache_control(response):
        """Parse Cache-Control header from response if it is set."""
        value = response.headers.get('Cache-Control', 'no-store').lower()

        if 'no-store' in value:
            seconds = 0
        else:
            max_age = re.match(r'.*max-age=\s*([0-9]+)\s*', value)
            if not max_age:
                seconds = 0
            else:
                seconds = int(max_age.groups()[0])
        return time.time() + seconds

    @staticmethod
    def _parse_etag(response):
        """Parse ETag header from response if it is set."""
        value = response.headers.get('ETag')

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
        status_str = {True: 'expired', False: 'fresh'}
        result = self._expires < time.time()
        _trace('Cached data %s for %s', status_str[result], self)
        return result

    @property
    def status_ok(self):
        return self._status_code >= 200 and self._status_code < 400

    @property
    def etag_headers(self):
        if self._etag is not None:
            return {'If-None-Match': self._etag}
        else:
            return {}

    def updated(self, response):
        if self._etag is None:
            return False
        elif self.url != response.url:
            logger.error(
                'ETag mismatch (different URI) for %s %s', self, response)
            return False
        elif not response.status_ok:
            logger.debug(
                'ETag mismatch (bad response) for %s %s', self, response)
            return False
        elif response._status_code != 304:
            _trace('ETag mismatch for %s %s', self, response)
            return False

        _trace('ETag match for %s %s', self, response)
        self._expires = response._expires
        self._etag = response._etag
        return True

    def __str__(self):
        return 'URL: %s ETag: %s Expires: %s' % (
            self.url, self._etag, datetime.fromtimestamp(self._expires))


class SpotifyOAuthClient(OAuthClient):

    TRACK_FIELDS = (
        'next,items(track(type,uri,name,duration_ms,disc_number,track_number,'
        'artists,album,is_playable,linked_from.uri))'
    )
    PLAYLIST_FIELDS = (
        'name,owner.id,type,uri,snapshot_id,tracks(%s),' % TRACK_FIELDS
    )

    def __init__(self, client_id, client_secret, proxy_config):
        super(SpotifyOAuthClient, self).__init__(
            base_url='https://api.spotify.com/v1',
            refresh_url='https://auth.mopidy.com/spotify/token',
            client_id=client_id, client_secret=client_secret,
            proxy_config=proxy_config)
        self.user_id = None

    def get_all(self, path, *args, **kwargs):
        while path is not None:
            logger.debug('Fetching page "%s"', path)
            result = self.get(path, *args, **kwargs)
            path = result.get('next')
            yield result

    def login(self):
        self.user_id = self.get('me').get('id')
        if self.user_id is None:
            logger.error('Failed to load Spotify user profile')
            return False
        else:
            logger.info('Logged into Spotify Web API as %s', self.user_id)
            return True

    def get_user_playlists(self, cache=None):
        with utils.time_logger('get_user_playlists'):
            pages = self.get_all('me/playlists', cache=cache, params={
                'limit': 50})
            for page in pages:
                for playlist in page.get('items', []):
                    yield playlist

    def get_playlist(self, uri, cache=None):
        try:
            parsed = parse_uri(uri)
            if parsed.type != 'playlist':
                raise ValueError(
                    'Could not parse %r as a Spotify playlist URI' % uri)
        except ValueError as exc:
            logger.error(exc)
            return {}

        playlist = self.get('playlists/%s' % parsed.id, cache=cache, params={
            'fields': self.PLAYLIST_FIELDS,
            'market': 'from_token'})

        tracks_path = playlist.get('tracks', {}).get('next')
        track_pages = self.get_all(tracks_path, cache=cache, params={
            'fields': self.TRACK_FIELDS,
            'market': 'from_token'})

        more_tracks = []
        for page in track_pages:
            more_tracks += page.get('items', [])
        if more_tracks:
            # Take a copy to avoid changing the cached response.
            playlist = copy.deepcopy(playlist)
            playlist.setdefault('tracks', {}).setdefault('items', [])
            playlist['tracks']['items'] += more_tracks

        return playlist


WebLink = collections.namedtuple('WebLink', ['uri', 'type', 'id', 'owner'])


# TODO: Make a WebSession class method?
def parse_uri(uri):
    parsed_uri = urlparse.urlparse(uri)

    schemes = ('http', 'https')
    netlocs = ('open.spotify.com', 'play.spotify.com')

    if parsed_uri.scheme == 'spotify':
        parts = parsed_uri.path.split(':')
    elif parsed_uri.scheme in schemes and parsed_uri.netloc in netlocs:
        parts = parsed_uri.path[1:].split('/')
    else:
        parts = []

    # Strip out empty parts to ensure we are strict about URI parsing.
    parts = [p for p in parts if p.strip()]

    if len(parts) == 2 and parts[0] in (
            'track', 'album', 'artist', 'playlist'):
        return WebLink(uri, parts[0],  parts[1], None)
    elif len(parts) == 3 and parts[0] == 'user' and parts[2] == 'starred':
        if parsed_uri.scheme == 'spotify':
            return WebLink(uri, 'playlist',  None, parts[1])
    elif len(parts) == 3 and parts[0] == 'playlist':
        return WebLink(uri, 'playlist',  parts[2], parts[1])
    elif len(parts) == 4 and parts[0] == 'user' and parts[2] == 'playlist':
        return WebLink(uri, 'playlist',  parts[3], parts[1])

    raise ValueError('Could not parse %r as a Spotify URI' % uri)
