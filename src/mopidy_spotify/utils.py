import contextlib
import itertools
import logging
import operator
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


def group_by_type(links):
    link_type_getter = operator.attrgetter("type")
    links = sorted((u for u in links if u), key=link_type_getter)
    yield from itertools.groupby(links, link_type_getter)


def batched(iterable, n):
    """
    Split into chunks of size n.
    batched('ABCDEFG', 3) → ABC DEF G
    """
    if n < 1:
        msg = "n must be at least one"
        raise ValueError(msg)
    it = iter(iterable)
    while batch := tuple(itertools.islice(it, n)):
        yield batch
