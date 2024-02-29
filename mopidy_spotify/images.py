import itertools
import logging
import operator
import urllib.parse

from mopidy_spotify.browse import BROWSE_DIR_URIS
from mopidy_spotify.translator import web_to_image

_API_MAX_IDS_PER_REQUEST = 50

_cache = {}  # (type, id) -> [Image(), ...]

logger = logging.getLogger(__name__)


def get_images(web_client, uris):
    result = {}
    uri_type_getter = operator.itemgetter("type")
    uris = (_parse_uri(u) for u in uris)
    uris = sorted((u for u in uris if u), key=uri_type_getter)
    for uri_type, group in itertools.groupby(uris, uri_type_getter):
        batch = []
        for uri in group:
            if uri["key"] in _cache:
                result[uri["uri"]] = _cache[uri["key"]]
            elif uri_type == "playlist":
                result.update(_process_uri(web_client, uri))
            else:
                batch.append(uri)
                if len(batch) >= _API_MAX_IDS_PER_REQUEST:
                    result.update(_process_uris(web_client, uri_type, batch))
                    batch = []
        result.update(_process_uris(web_client, uri_type, batch))
    return result


def _parse_uri(uri):
    if uri in BROWSE_DIR_URIS:
        return  # These are internal to the extension.
    try:
        parsed_uri = urllib.parse.urlparse(uri)
        uri_type, uri_id = None, None

        if parsed_uri.scheme == "spotify":
            fragments = parsed_uri.path.split(":")
            if len(fragments) < 2:
                raise ValueError("Too few fragments")
            uri_type, uri_id = parsed_uri.path.split(":")[:2]
        elif parsed_uri.scheme in ("http", "https"):
            if parsed_uri.netloc in ("open.spotify.com", "play.spotify.com"):
                uri_type, uri_id = parsed_uri.path.split("/")[1:3]

        supported_types = ("track", "album", "artist", "playlist")
        if uri_type:
            if uri_type not in supported_types:
                logger.warning(
                    f"Unsupported image type '{uri_type}' in {repr(uri)}"
                )
                return
            elif uri_id:
                return {
                    "uri": uri,
                    "type": uri_type,
                    "id": uri_id,
                    "key": (uri_type, uri_id),
                }
        raise ValueError("Unknown error")
    except Exception as e:
        logger.exception(f"Could not parse {repr(uri)} as a Spotify URI ({e})")


def _process_uri(web_client, uri):
    data = web_client.get(f"{uri['type']}s/{uri['id']}")
    _cache[uri["key"]] = tuple(
        web_to_image(i) for i in data.get("images") or []
    )
    return {uri["uri"]: _cache[uri["key"]]}


def _process_uris(web_client, uri_type, uris):
    result = {}
    ids = [u["id"] for u in uris]
    ids_to_uris = {u["id"]: u for u in uris}

    if not uris:
        return result

    data = web_client.get(uri_type + "s", params={"ids": ",".join(ids)})
    for item in (
        data.get(
            uri_type + "s",
        )
        or []
    ):
        if not item:
            continue

        if "linked_from" in item:
            item_id = item["linked_from"].get("id")
        else:
            item_id = item.get("id")
        uri = ids_to_uris.get(item_id)
        if not uri:
            continue

        if uri["key"] not in _cache:
            if uri_type == "track":
                if "album" not in item:
                    continue
                album = _parse_uri(item["album"].get("uri"))
                if not album:
                    continue
                album_key = album["key"]
                if album_key not in _cache:
                    _cache[album_key] = tuple(
                        web_to_image(i)
                        for i in item["album"].get("images") or []
                    )
                _cache[uri["key"]] = _cache[album_key]
            else:
                _cache[uri["key"]] = tuple(
                    web_to_image(i) for i in item.get("images") or []
                )
        result[uri["uri"]] = _cache[uri["key"]]

    return result
