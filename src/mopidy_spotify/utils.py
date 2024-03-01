import contextlib
import logging
import time

import requests
from mopidy import httpclient

from mopidy_spotify import Extension, __version__

logger = logging.getLogger(__name__)
TRACE = logging.getLevelName("TRACE")


def get_requests_session(proxy_config):
    user_agent = f"{Extension.dist_name}/{__version__}"
    proxy = httpclient.format_proxy(proxy_config)
    full_user_agent = httpclient.format_user_agent(user_agent)

    session = requests.Session()
    session.proxies.update({"http": proxy, "https": proxy})
    session.headers.update({"user-agent": full_user_agent})

    return session


@contextlib.contextmanager
def time_logger(name, level=TRACE):
    start = time.time()
    yield
    end = time.time() - start
    logger.log(level, f"{name} took {int(end * 1000)}ms")


def flatten(list_of_lists):
    return [item for sublist in list_of_lists for item in sublist]
