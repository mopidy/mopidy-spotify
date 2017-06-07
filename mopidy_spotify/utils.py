from __future__ import unicode_literals

import contextlib
import logging
import time

from mopidy import httpclient

import requests

from mopidy_spotify import Extension, __version__


logger = logging.getLogger(__name__)
TRACE = logging.getLevelName('TRACE')


def get_requests_session(proxy_config):
    user_agent = '%s/%s' % (Extension.dist_name, __version__)
    proxy = httpclient.format_proxy(proxy_config)
    full_user_agent = httpclient.format_user_agent(user_agent)

    session = requests.Session()
    session.proxies.update({'http': proxy, 'https': proxy})
    session.headers.update({'user-agent': full_user_agent})

    return session


@contextlib.contextmanager
def time_logger(name, level=TRACE):
    start = time.time()
    yield
    logger.log(level, '%s took %dms', name, (time.time() - start) * 1000)
