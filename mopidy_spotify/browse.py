import logging

from mopidy import models

import spotify
from mopidy_spotify import countries, playlists, translator
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
    models.Ref.directory(uri="spotify:top:albums", name="Top albums"),
    models.Ref.directory(uri="spotify:top:artists", name="Top artists"),
]

_YOUR_MUSIC_DIR_CONTENTS = [
    models.Ref.directory(uri="spotify:your:tracks", name="Your tracks"),
    models.Ref.directory(uri="spotify:your:albums", name="Your albums"),
]

_PLAYLISTS_DIR_CONTENTS = [
    models.Ref.directory(uri="spotify:playlists:featured", name="Featured"),
]

_TOPLIST_TYPES = {
    "albums": spotify.ToplistType.ALBUMS,
    "artists": spotify.ToplistType.ARTISTS,
    "tracks": spotify.ToplistType.TRACKS,
}

_TOPLIST_REGIONS = {
    "country": lambda session: session.user_country,
    "everywhere": lambda session: spotify.ToplistRegion.EVERYWHERE,
}


def browse(*, config, session, web_client, uri):
    if uri == ROOT_DIR.uri:
        return _ROOT_DIR_CONTENTS
    elif uri == _TOP_LIST_DIR.uri:
        return _TOP_LIST_DIR_CONTENTS
    elif uri == _YOUR_MUSIC_DIR.uri:
        return _YOUR_MUSIC_DIR_CONTENTS
    elif uri == _PLAYLISTS_DIR.uri:
        return _PLAYLISTS_DIR_CONTENTS
    elif uri.startswith("spotify:user:") or uri.startswith("spotify:playlist:"):
        return _browse_playlist(session, web_client, uri, config)
    elif uri.startswith("spotify:album:"):
        return _browse_album(session, uri, config)
    elif uri.startswith("spotify:artist:"):
        return _browse_artist(session, uri, config)
    elif uri.startswith("spotify:top:"):
        parts = uri.replace("spotify:top:", "").split(":")
        if len(parts) == 1:
            return _browse_toplist_regions(variant=parts[0])
        elif len(parts) == 2:
            if parts[1] == "user":
                return _browse_toplist_user(web_client, variant=parts[0])
            return _browse_toplist(
                config, session, variant=parts[0], region=parts[1]
            )
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


def _browse_playlist(session, web_client, uri, config):
    return playlists.playlist_lookup(
        session, web_client, uri, config["bitrate"], as_items=True
    )


def _browse_album(session, uri, config):
    sp_album_browser = session.get_album(uri).browse()
    sp_album_browser.load(config["timeout"])
    return list(
        translator.to_track_refs(
            sp_album_browser.tracks, timeout=config["timeout"]
        )
    )


def _browse_artist(session, uri, config):
    sp_artist_browser = session.get_artist(uri).browse(
        type=spotify.ArtistBrowserType.NO_TRACKS
    )
    sp_artist_browser.load(config["timeout"])
    top_tracks = list(
        translator.to_track_refs(
            sp_artist_browser.tophit_tracks, timeout=config["timeout"]
        )
    )
    albums = list(
        translator.to_album_refs(
            sp_artist_browser.albums, timeout=config["timeout"]
        )
    )
    return top_tracks + albums


def _browse_toplist_regions(variant):
    dir_contents = [
        models.Ref.directory(
            uri=f"spotify:top:{variant}:country", name="Country"
        ),
        models.Ref.directory(
            uri=f"spotify:top:{variant}:countries", name="Other countries"
        ),
        models.Ref.directory(
            uri=f"spotify:top:{variant}:everywhere", name="Global"
        ),
    ]
    if variant in ("tracks", "artists"):
        dir_contents.insert(
            0,
            models.Ref.directory(
                uri=f"spotify:top:{variant}:user", name="Personal"
            ),
        )
    return dir_contents


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


def _browse_toplist(config, session, variant, region):
    if region == "countries":
        codes = config["toplist_countries"]
        if not codes:
            codes = countries.COUNTRIES.keys()
        return [
            models.Ref.directory(
                uri=f"spotify:top:{variant}:{code.lower()}",
                name=countries.COUNTRIES.get(code.upper(), code.upper()),
            )
            for code in codes
        ]

    if region in ("country", "everywhere"):
        sp_toplist = session.get_toplist(
            type=_TOPLIST_TYPES[variant],
            region=_TOPLIST_REGIONS[region](session),
        )
    elif len(region) == 2:
        sp_toplist = session.get_toplist(
            type=_TOPLIST_TYPES[variant], region=region.upper()
        )
    else:
        return []

    if session.connection.state is spotify.ConnectionState.LOGGED_IN:
        sp_toplist.load(config["timeout"])

    if not sp_toplist.is_loaded:
        return []

    if variant == "tracks":
        return list(translator.to_track_refs(sp_toplist.tracks))
    elif variant == "albums":
        return list(
            translator.to_album_refs(
                sp_toplist.albums, timeout=config["timeout"]
            )
        )
    elif variant == "artists":
        return list(
            translator.to_artist_refs(
                sp_toplist.artists, timeout=config["timeout"]
            )
        )
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
