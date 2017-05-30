from __future__ import unicode_literals

import logging
import time

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

    def __init__(self, refresh_url, client_id=None, client_secret=None,
                 proxy_config=None, expiry_margin=60):

        if client_id and client_secret:
            self._auth = (client_id, client_secret)
        else:
            self._auth = None

        self._refresh_url = refresh_url

        self._margin = expiry_margin
        self._expires = 0

        self._headers = {'Content-Type': 'application/json'}
        self._session = utils.get_requests_session(proxy_config or {})

    def _request(self, method, url, **kwargs):
        try:
            resp = self._session.request(method=method, url=url, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            raise OAuthClientError('Fetching %s failed: %s' % (url, e))

    def _decode(self, resp):
        try:
            return resp.json()
        except ValueError as e:
            raise OAuthClientError('JSON decoding %s failed: %s' % (
                resp.request.url, e))

    def _should_refresh_token(self):
        return not self._auth or time.time() > self._expires - self._margin

    def _refresh_token(self):
        logger.debug('Fetching OAuth token from %s', self._refresh_url)

        resp = self._request('POST', self._refresh_url, auth=self._auth,
                             data={'grant_type': 'client_credentials'})
        data = self._decode(resp)

        if data.get('error'):
            raise OAuthTokenRefreshError('%s %s' % (
                data['error'], data.get('error_description', '')))
        elif not data.get('access_token'):
            raise OAuthTokenRefreshError('missing access_token')
        elif data.get('token_type') != 'Bearer':
            raise OAuthTokenRefreshError('wrong token_type: %s' %
                                         data.get('token_type'))

        self._headers['Authorization'] = 'Bearer %s' % data['access_token']
        self._expires = time.time() + data.get('expires_in', float('Inf'))

        if data.get('expires_in'):
            logger.debug('Token expires in %s seconds.', data['expires_in'])
        if data.get('scope'):
            logger.debug('Token scopes: %s', data['scope'])

    def get(self, url, **kwargs):
        result = {}
        try:
            if self._should_refresh_token():
                self._refresh_token()
            kwargs.setdefault('headers', {}).update(self._headers)
            response = self._request('GET', url, **kwargs)
            result = self._decode(response)
        except (OAuthTokenRefreshError, OAuthClientError) as e:
            logger.error(e)

        return result
