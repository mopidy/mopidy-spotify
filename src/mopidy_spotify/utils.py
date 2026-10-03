from __future__ import annotations

import contextlib
import itertools
import logging
import operator
import time
from typing import TYPE_CHECKING

import requests
from mopidy import httpclient

from mopidy_spotify import Extension, __version__

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

    from mopidy.config import ProxyConfig

    from mopidy_spotify.web import LinkType, WebLink

logger = logging.getLogger(__name__)
TRACE = logging.getLevelName("TRACE")


def get_requests_session(
    proxy_config: ProxyConfig | None,
) -> requests.Session:
    user_agent = f"{Extension.dist_name}/{__version__}"
    proxy = httpclient.format_proxy(proxy_config) if proxy_config else None
    full_user_agent = httpclient.format_user_agent(user_agent)

    session = requests.Session()
    session.proxies.update({"http": proxy, "https": proxy})  # pyright: ignore[reportCallIssue, reportArgumentType]
    session.headers.update({"user-agent": full_user_agent})

    return session


@contextlib.contextmanager
def time_logger(name: str, level: int = TRACE) -> Generator[None]:
    start = time.time()
    yield
    end = time.time() - start
    logger.log(level, f"{name} took {int(end * 1000)}ms")


def flatten[T](list_of_lists: Iterable[Iterable[T]]) -> list[T]:
    return [item for sublist in list_of_lists for item in sublist]


def group_by_type(
    links: Iterable[WebLink | None],
) -> Generator[tuple[LinkType, Iterable[WebLink]]]:
    link_type_getter = operator.attrgetter("type")
    filtered: list[WebLink] = [u for u in links if u is not None]
    yield from itertools.groupby(
        sorted(filtered, key=link_type_getter), link_type_getter
    )
