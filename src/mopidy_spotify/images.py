import logging

from mopidy_spotify.browse import BROWSE_DIR_URIS
from mopidy_spotify.translator import web_to_image
from mopidy_spotify.utils import group_by_type
from mopidy_spotify.web import LinkType, WebLink

SUPPORTED_TYPES = (
    LinkType.TRACK,
    LinkType.ALBUM,
    LinkType.ARTIST,
    LinkType.PLAYLIST,
)

_cache = {}  # (type, id) -> [Image(), ...]

logger = logging.getLogger(__name__)


def get_images(web_client, uris):
    result = {}
    links = (_parse_uri(u) for u in uris)
    for link_type, link_group in group_by_type(links):
        batch = []
        for link in link_group:
            key = _make_cache_key(link)
            if key in _cache:
                result[link.uri] = _cache[key]
            elif link_type == LinkType.PLAYLIST:
                result.update(_process_one(web_client, link))
            else:
                batch.append(link)
        result.update(_process_many(web_client, link_type, batch))
    return result


def _make_cache_key(link):
    return (link.type, link.id)


def _parse_uri(uri):
    if uri in BROWSE_DIR_URIS:
        return None  # These are internal to the extension.
    try:
        link = WebLink.from_uri(uri)
        if link.type not in SUPPORTED_TYPES:
            msg = f"Unsupported image type '{link.type}' in {uri!r}"
            raise ValueError(msg)  # noqa: TRY301
        if not link.id:
            msg = "ID missing"
            raise ValueError(msg)  # noqa: TRY301
    except Exception as e:
        logger.exception(f"Could not parse {uri!r} as a Spotify URI ({e!s})")  # noqa: TRY401
        return None

    return link


def _process_one(web_client, link):
    data = web_client.get(f"{link.type}s/{link.id}")
    key = _make_cache_key(link)
    _cache[key] = tuple(web_to_image(i) for i in data.get("images") or [])
    return {link.uri: _cache[key]}


def _process_many(
    web_client,
    link_type,
    links,
):
    result = {}
    if not links:
        return result

    for link, item in web_client.get_batch(link_type, links):
        key = _make_cache_key(link)
        if link_type == LinkType.TRACK:
            if not (album_item := item.get("album")):
                continue
            if not (album_link := _parse_uri(album_item.get("uri"))):
                continue
            album_key = _make_cache_key(album_link)
            if album_key not in _cache:
                _cache[album_key] = tuple(
                    web_to_image(i) for i in album_item.get("images") or []
                )
            _cache[key] = _cache[album_key]
        else:
            _cache[key] = tuple(web_to_image(i) for i in item.get("images") or [])
        result[link.uri] = _cache[key]

    return result
