import logging

from mopidy import models

from mopidy_spotify import playlists, translator
from mopidy_spotify.web import WebLink
from mopidy_spotify.utils import flatten

logger = logging.getLogger(__name__)

ROOT_DIR = models.Ref.directory(uri="spotify:directory", name="Spotify")

_TOP_LIST_DIR = models.Ref.directory(uri="spotify:top", name="Top lists")
_YOUR_MUSIC_DIR = models.Ref.directory(uri="spotify:your", name="Your music")
_PLAYLISTS_DIR = models.Ref.directory(uri="spotify:playlists", name="Playlists")

_ROOT_DIR_CONTENTS = [
    _TOP_LIST_DIR,
    _YOUR_MUSIC_DIR,
    _PLAYLISTS_DIR,
]

_TOP_LIST_DIR_CONTENTS = [
    models.Ref.directory(uri="spotify:top:tracks", name="Top tracks"),
    models.Ref.directory(uri="spotify:top:artists", name="Top artists"),
]

_YOUR_MUSIC_DIR_CONTENTS = [
    models.Ref.directory(uri="spotify:your:tracks", name="Your tracks"),
    models.Ref.directory(uri="spotify:your:albums", name="Your albums"),
]

_PLAYLISTS_DIR_CONTENTS = [
    models.Ref.directory(uri="spotify:playlists:featured", name="Featured"),
]


def browse(*, config, session, web_client, uri):
    if uri == ROOT_DIR.uri:
        return _ROOT_DIR_CONTENTS
    elif uri == _TOP_LIST_DIR.uri:
        return _TOP_LIST_DIR_CONTENTS
    elif uri == _YOUR_MUSIC_DIR.uri:
        return _YOUR_MUSIC_DIR_CONTENTS
    elif uri == _PLAYLISTS_DIR.uri:
        return _PLAYLISTS_DIR_CONTENTS

    if web_client is None or not web_client.logged_in:
        return []

    # TODO: Support for category browsing.
    if uri.startswith("spotify:user:") or uri.startswith("spotify:playlist:"):
        return _browse_playlist(web_client, uri)
    elif uri.startswith("spotify:album:"):
        return _browse_album(web_client, uri)
    elif uri.startswith("spotify:artist:"):
        return _browse_artist(web_client, uri)
    elif uri.startswith("spotify:top:"):
        parts = uri.replace("spotify:top:", "").split(":")
        if len(parts) == 1:
            return _browse_toplist_user(web_client, variant=parts[0])
        else:
            logger.info(f"Failed to browse {uri!r}: Toplist URI parsing failed")
            return []
    elif uri.startswith("spotify:your:"):
        parts = uri.replace("spotify:your:", "").split(":")
        if len(parts) == 1:
            return _browse_your_music(web_client, variant=parts[0])
    elif uri.startswith("spotify:playlists:"):
        parts = uri.replace("spotify:playlists:", "").split(":")
        if len(parts) == 1:
            return _browse_playlists(web_client, variant=parts[0])

    logger.info(f"Failed to browse {uri!r}: Unknown URI type")
    return []


def _browse_playlist(web_client, uri):
    return playlists.playlist_lookup(web_client, uri, None, as_items=True)


def _browse_album(web_client, uri):
    try:
        link = WebLink.from_uri(uri)
    except ValueError as exc:
        logger.info(f"Failed to browse {uri!r}: {exc}")
        return []

    web_album = web_client.get_album(link)
    web_tracks = web_album.get("tracks", {}).get("items", [])
    return list(translator.web_to_track_refs(web_tracks))


def _browse_artist(web_client, uri):
    try:
        link = WebLink.from_uri(uri)
    except ValueError as exc:
        logger.info(f"Failed to browse {uri!r}: {exc}")
        return []

    web_top_tracks = web_client.get_artist_top_tracks(link)
    top_tracks = list(translator.web_to_track_refs(web_top_tracks))

    web_albums = web_client.get_artist_albums(link, all_tracks=False)
    albums = list(translator.web_to_album_refs(web_albums))

    return top_tracks + albums


def _browse_toplist_user(web_client, variant):
    if not web_client.logged_in:
        return []

    if variant in ("tracks", "artists"):
        items = flatten(
            [
                page.get("items", [])
                for page in web_client.get_all(
                    f"me/top/{variant}",
                    params={"limit": 50},
                )
                if page
            ]
        )
        if variant == "tracks":
            return list(
                translator.web_to_track_refs(items, check_playable=False)
            )
        else:
            return list(translator.web_to_artist_refs(items))
    else:
        return []


def _load_your_music(web_client, variant):
    if web_client is None or not web_client.logged_in:
        return

    if variant not in ("tracks", "albums"):
        return

    results = web_client.get_all(
        f"me/{variant}",
        params={"market": "from_token", "limit": 50},
    )
    for page in results:
        if not page:
            continue
        items = page.get("items", [])
        for item in items:
            yield item


def _browse_your_music(web_client, variant):
    items = _load_your_music(web_client, variant)
    if variant == "tracks":
        return list(translator.web_to_track_refs(items))
    elif variant == "albums":
        return list(translator.web_to_album_refs(items))
    else:
        return []


def _browse_playlists(web_client, variant):
    if not web_client.logged_in:
        return []

    if variant == "featured":
        items = flatten(
            [
                page.get("playlists", {}).get("items", [])
                for page in web_client.get_all(
                    "browse/featured-playlists",
                    params={"limit": 50},
                )
                if page
            ]
        )
        return list(translator.to_playlist_refs(items))
    else:
        return []
