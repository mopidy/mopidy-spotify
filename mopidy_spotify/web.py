from __future__ import unicode_literals

import email
import logging
import os
import re
import time
import urllib
import urlparse

import collections
import requests

from mopidy_spotify import utils, translator

logger = logging.getLogger(__name__)


class memoized(object):
    def __init__(self, func):
        self.func = func
        self.cache = {}

    def __call__(self, *args, **kwargs):
        # NOTE Only args, not kwargs, are part of the memoization key.
        if not isinstance(args, collections.Hashable):
            return self.func(*args, **kwargs)
        if args in self.cache:
            logger.info("Cache hit for %S" % ','.join(args))
            return self.cache[args]
        else:
            value = self.func(*args, **kwargs)
            if value is not None:
                self.cache[args] = value
            return value


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
        return result

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
                result = self._decode(response)

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
