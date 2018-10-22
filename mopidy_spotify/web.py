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

from contextlib import contextmanager
from datetime import datetime

import requests

from mopidy.internal import log
from mopidy_spotify import utils

logger = logging.getLogger(__name__)


def _trace(*args, **kwargs):
    logger.log(log.TRACE_LOG_LEVEL, *args, **kwargs)


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

        cached_result = None
        if cache is not None:
            cached_result = cache.get(path)
            if cached_result:
                if cached_result.is_valid:
                    _trace('Cached data still valid for %s', cached_result)
                    return cached_result
                elif cached_result.etag:
                    _trace('Using etag for %s', cached_result)
                    kwargs.setdefault('headers', {}).update({'If-None-Match': cached_result.etag})

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
            if cached_result and cached_result.still_valid(result):
                return cached_result
            else:
                cache[path] = result

        return result

    def _should_cache_response(self, cache, response):
        if cache is not None:
            return response.status_code >= 200 and response.status_code < 400

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
                expires = None
                result = None
            else:
                status_code = response.status_code
                backoff_time = self._parse_retry_after(response)
                expires = self._parse_cache_control(response)
                etag = self._parse_etag(response)
                data = self._decode(response)
                result = WebResponse(prepared_request.url, data, expires, etag, status_code)

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

    def _decode(self, response):
        # Deal with 204 and other responses with empty body.
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as e:
            url = response.request.url
            logger.error('JSON decoding %s failed: %s', url, e)
            return None

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

    def _parse_cache_control(self, response):
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

    def _parse_etag(self, response):
        """Parse ETag header from response if it is set."""
        value = response.headers.get('ETag')

        if value:
            # 'W/' (case-sensitive) indicates that a weak validator is used,
            # currently ignoring this.
            # Format is string of ASCII characters placed between double quotes
            # but can seemingly also include hyphen characters.
            etag = re.match(r'^(W/)?("[!-~]+")$', value)
            if etag and len(etag.groups()) == 2:
                return etag.groups()[1]


class WebResponse(dict):

    def __init__(self, url, data, expires=0.0, etag=None, status_code=400):
        self.url = url
        self._expires = expires
        self.etag = etag
        self.status_code = status_code
        self._is_cached = False
        super(WebResponse, self).__init__(data or {})

    @property
    def is_valid(self):
        return self._expires > time.time()

    def still_valid(self, response):
        if response.status_code == 304:
            self._expires = response._expires
            self.etag = response.etag
            return True
        else:
            _trace('Changed WebResponse %s', self)

    def __str__(self):
        return 'URL: %s ETag: %s Expires: %s' % (
            self.url, self.etag, datetime.fromtimestamp(self._expires))


class WebResponseCache(dict):

    def __init__(self, *args, **kwargs):
        super(WebResponseCache, self).__init__(*args, **kwargs)
        self._force_expiry = None

    def __setitem__(self, url, response):
        if not isinstance(response, WebResponse):
            return

        if response._is_cached:
            return

        response._is_cached = True
        if self._force_expiry is not None:
            response._expires = self._force_expiry
        super(WebResponseCache, self).__setitem__(url, response)

    @contextmanager
    def expiry_override(self, seconds=30):
        logger.debug('Forcing cache expiry to %d seconds from now', seconds)
        old_expiry = self._force_expiry
        self._force_expiry = time.time() + seconds
        yield
        self._force_expiry = old_expiry


TRACK_FIELDS = ['type', 'uri', 'name', 'duration_ms', 'disc_number', 'track_number', 'artists', 'album', 'is_playable', 'linked_from.uri']
TRACKS_PAGE = ','.join(['next', 'items(track(' + ','.join(TRACK_FIELDS) + '))'])
PLAYLIST_FIELDS = ','.join(['name', 'owner.id', 'type', 'uri', 'tracks(%s)' % TRACKS_PAGE])


class WebSession(object):

    def __init__(self, client_id, client_secret, proxy_config):
        # TODO: Separate caches so can persist/clear them separately?
        self._cache = WebResponseCache()
        self._client = OAuthClient(
            base_url='https://api.spotify.com/v1',
            refresh_url='https://auth.mopidy.com/spotify/token',
            client_id=client_id, client_secret=client_secret,
            proxy_config=proxy_config)
        self.playlists_loaded = False
        self.user_name = self._client.get('me').get('id')
        if self.user_name is None:
            logger.error('Failed to load Spotify user profile')
        else:
            logger.info('Logged into Spotify Web API as %s', self.user_name)

    def _get_pages(self, url, cache, *args, **kwargs):
        while url is not None:
            result = self._client.get(url, cache, *args, **kwargs)
            url = result.get('next')
            yield result

    def load_playlists(self):
        self.playlists_loaded = False
        count = 0
        with self._cache.expiry_override(30):
            for playlist in self.get_user_playlists(self.user_name):
                self.get_playlist(playlist.get('uri'))
                count += 1
        logger.info('Loaded %d playlists', count)
        self.playlists_loaded = True

    def get_playlist(self, uri):
        try:
            link = parse_uri(uri)
        except ValueError as exc:
            logger.info(exc)
            return {}

        with utils.time_logger('get_playlist(%s)' % uri):
            url = 'users/%s/playlists/%s' % (link.owner, link.id)
            params = {'fields': PLAYLIST_FIELDS, 'market': 'from_token'}
            web_playlist = self._client.get(url, self._cache, params=params)

            more_tracks = []
            tracks_url = web_playlist.get('tracks', {}).get('next')
            # Spotify's response omits our fields in this *first* paging link.
            params['fields'] = TRACKS_PAGE
            for tracks_page in self._get_pages(tracks_url, self._cache, params=params):
                more_tracks += tracks_page.get('items', [])

            if len(more_tracks) > 0:
                # Copy result data to avoid changing what's in the cache.
                web_playlist = copy.deepcopy(web_playlist)
                web_playlist['tracks']['items'] += more_tracks

            return web_playlist

    def get_user_playlists(self, username=None, include_tracks=True):
        username = username or self.user_name
        if username is None:
            return

        with utils.time_logger('get_user_playlists(%s, %s)' % (username, include_tracks)):
            url = 'users/%s/playlists' % username
            for page in self._get_pages(url, self._cache):
                for web_playlist in page.get('items', []):
                    uri = web_playlist.get('uri')
                    if uri and include_tracks:
                        web_playlist = self.get_playlist(uri)
                    yield web_playlist


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

    if len(parts) == 2 and parts[0] in ('track', 'album', 'artist', 'playlist'):
        return WebLink(uri, parts[0],  parts[1], None)
    elif len(parts) == 3 and parts[0] == 'user' and parts[2] == 'starred':
        if parsed_uri.scheme == 'spotify':
            return WebLink(uri, 'playlist',  None, parts[1])
    elif len(parts) == 3 and parts[0] == 'playlist':
        return WebLink(uri, 'playlist',  parts[2], parts[1])
    elif len(parts) == 4 and parts[0] == 'user' and parts[2] == 'playlist':
        return WebLink(uri, 'playlist',  parts[3], parts[1])

    raise ValueError('Could not parse %r as a Spotify URI' % uri)


def link_is_playlist(link):
    return link.type == 'playlist'
