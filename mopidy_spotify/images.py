import itertools
import logging
import operator
import urllib.parse

from mopidy import models

_API_MAX_IDS_PER_REQUEST = 50

_cache = {}  # (type, id) -> [Image(), ...]

logger = logging.getLogger(__name__)


def get_images(web_client, uris):
    result = {}
    uri_type_getter = operator.itemgetter("type")
    uris = sorted((_parse_uri(u) for u in uris), key=uri_type_getter)
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
    parsed_uri = urllib.parse.urlparse(uri)
    uri_type, uri_id = None, None

    if parsed_uri.scheme == "spotify":
        uri_type, uri_id = parsed_uri.path.split(":")[:2]
    elif parsed_uri.scheme in ("http", "https"):
        if parsed_uri.netloc in ("open.spotify.com", "play.spotify.com"):
            uri_type, uri_id = parsed_uri.path.split("/")[1:3]

    supported_types = ("track", "album", "artist", "playlist")
    if uri_type and uri_type in supported_types and uri_id:
        return {
            "uri": uri,
            "type": uri_type,
            "id": uri_id,
            "key": (uri_type, uri_id),
        }

    raise ValueError(f"Could not parse {repr(uri)} as a Spotify URI")


def _process_uri(web_client, uri):
    data = web_client.get(f"{uri['type']}s/{uri['id']}")
    _cache[uri["key"]] = tuple(_translate_image(i) for i in data["images"])
    return {uri["uri"]: _cache[uri["key"]]}


def _process_uris(web_client, uri_type, uris):
    result = {}
    ids = [u["id"] for u in uris]
    ids_to_uris = {u["id"]: u for u in uris}

    if not uris:
        return result

    data = web_client.get(uri_type + "s", params={"ids": ",".join(ids)})
    for item in data.get(uri_type + "s", []):
        if not item:
            continue

        if "linked_from" in item:
            uri = ids_to_uris[item["linked_from"]["id"]]
        else:
            uri = ids_to_uris[item["id"]]

        if uri["key"] not in _cache:
            if uri_type == "track":
                album_key = _parse_uri(item["album"]["uri"])["key"]
                if album_key not in _cache:
                    _cache[album_key] = tuple(
                        _translate_image(i) for i in item["album"]["images"]
                    )
                _cache[uri["key"]] = _cache[album_key]
            else:
                _cache[uri["key"]] = tuple(
                    _translate_image(i) for i in item["images"]
                )
        result[uri["uri"]] = _cache[uri["key"]]

    return result


def _translate_image(i):
    return models.Image(uri=i["url"], height=i["height"], width=i["width"])
