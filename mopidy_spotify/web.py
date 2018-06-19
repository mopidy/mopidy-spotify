from __future__ import unicode_literals

import collections
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

from mopidy_spotify import utils

logger = logging.getLogger(__name__)


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

    def get(self, path, *args, **kwargs):
        if self._authorization_failed:
            logger.debug('Blocking request as previous authorization failed.')
            return {}

        # Pop this first as we don't want to cache the refresh token.
        cache = kwargs.pop('cache', None)

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
        result = self._request_with_retries('GET', path, cache, *args, **kwargs)

        if result is None or 'error' in result:
            return {}

        if self._should_cache_response(cache, result):
            cache[result.url] = result

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

    def _request_with_retries(self, method, url, cache=None, *args, **kwargs):
        prepared_request = self._session.prepare_request(
            requests.Request(method, self._prepare_url(url, *args), **kwargs))

        if cache is not None:
            result = cache.get(prepared_request.url)
            if result is not None and not result.expired():
                logger.debug("Using cached data for %s", prepared_request.url)
                return result

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
                data = self._decode(response)
                result = WebResponse(prepared_request.url, data, expires, status_code)

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
        logger.debug("Expires in %d seconds (%s)", seconds, value)
        return time.time() + seconds


class WebResponse(dict):

    def __init__(self, url, data, expires=0.0, status_code=400):
        self.url = url
        self._expires = expires
        self.status_code = status_code
        self._is_cached = False
        super(WebResponse, self).__init__(data)

    def expired(self):
        return self._expires <= time.time()


class WebResponseCache(dict):

    def __init__(self, *args, **kwargs):
        super(WebResponseCache, self).__init__(*args, **kwargs)
        self._force_expiry = None

    def load(self):
        # TODO: Load persisted cache data
        pass

    def __setitem__(self, url, response):
        if not isinstance(response, WebResponse):
            return

        if response._is_cached:
            return

        response._is_cached = True
        if self._force_expiry is not None:
            response._expires = self._force_expiry
        logger.debug('Caching %s until %s', url, datetime.fromtimestamp(response._expires))
        super(WebResponseCache, self).__setitem__(url, response)

    @contextmanager
    def expiry_override(self, seconds=30):
        logger.debug('Forcing cache expiry to %d seconds from now', seconds)
        old_expiry = self._force_expiry
        self._force_expiry = time.time() + seconds
        yield
        self._force_expiry = old_expiry


TRACK_FIELDS = ['type', 'uri', 'name', 'duration_ms', 'disc_number', 'track_number', 'artists', 'album']
PLAYLIST_TRACK_FIELDS = 'tracks(next,items(track(' + ','.join(TRACK_FIELDS) + ')))'
PLAYLIST_FIELDS = ','.join(['name', 'owner.id', 'type', 'uri', PLAYLIST_TRACK_FIELDS])


class WebSession(object):

    def __init__(self, client_id, client_secret, proxy_config):
        # TODO: Separate caches so can persist them differently?
        self._cache = WebResponseCache()
        self._client = OAuthClient(
            base_url='https://api.spotify.com/v1',
            refresh_url='https://auth.mopidy.com/spotify/token',
            client_id=client_id, client_secret=client_secret,
            proxy_config=proxy_config)

    def login(self, username):
        # TODO: Test auth?
        self._cache.load()
        with self._cache.expiry_override(60):
            playlists = list(self.get_user_playlists(username))
            for playlist in playlists:
               self.get_playlist(playlist.get('uri'))
            logger.info('Loaded %d playlists', len(playlists))

    def _get_pages(self, url, *args, **kwargs):
        while url is not None:
            logger.debug('Fetching "%s"', url)
            result = self._client.get(url, *args, **kwargs)
            url = result.get('next')
            yield result

    def get_playlist(self, uri):
        try:
            link = parse_uri(uri)
        except ValueError as exc:
            logger.info(exc)
            return {}

        with utils.time_logger('get_playlist(%s)' % uri, logging.INFO):
            url = 'users/%s/playlists/%s' % (link.owner, link.id)
            params = {'fields': PLAYLIST_FIELDS, 'market': 'from_token'}
            web_playlist = self._client.get(url, params=params, cache=self._cache)
            tracks_url = web_playlist.get('tracks', {}).get('next')
            for page in self._get_pages(tracks_url, cache=self._cache):
                web_playlist['tracks']['items'] += page.get('items', [])
            return web_playlist

    def get_user_playlists(self, username, include_tracks=True):
        with utils.time_logger('get_user_playlists(%s, %s)' % (username, include_tracks), logging.INFO):
            url = 'users/%s/playlists' % username
            for page in self._get_pages(url, cache=self._cache):
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

    if len(parts) == 2 and parts[0] in ('track', 'album', 'artist'):
        return WebLink(uri, parts[0],  parts[1], None)
    elif len(parts) == 3 and parts[0] == 'user' and parts[2] == 'starred':
        if parsed_uri.scheme == 'spotify':
            return WebLink(uri, 'starred',  None, parts[1])
    elif len(parts) == 3 and parts[0] == 'playlist':
        return WebLink(uri, 'playlist',  parts[2], parts[1])
    elif len(parts) == 4 and parts[0] == 'user' and parts[2] == 'playlist':
        return WebLink(uri, 'playlist',  parts[3], parts[1])

    raise ValueError('Could not parse %r as a Spotify URI' % uri)

