import logging

from mopidy import models

import spotify
from mopidy_spotify import countries, translator

logger = logging.getLogger(__name__)

ROOT_DIR = models.Ref.directory(uri="spotify:directory", name="Spotify")

_TOPLIST_DIR = models.Ref.directory(uri="spotify:top:lists", name="Top lists")

_ROOT_DIR_CONTENTS = [
    _TOPLIST_DIR,
]

_TOPLIST_DIR_CONTENTS = [
    models.Ref.directory(uri="spotify:top:tracks", name="Top tracks"),
    models.Ref.directory(uri="spotify:top:albums", name="Top albums"),
    models.Ref.directory(uri="spotify:top:artists", name="Top artists"),
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
    elif uri == _TOPLIST_DIR.uri:
        return _TOPLIST_DIR_CONTENTS
    elif uri.startswith("spotify:user:"):
        return _browse_playlist(session, uri, config)
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
    else:
        logger.info(f"Failed to browse {uri!r}: Unknown URI type")
        return []


def _browse_playlist(session, uri, config):
    sp_playlist = session.get_playlist(uri)
    sp_playlist.load(config["timeout"])
    return list(
        translator.to_track_refs(sp_playlist.tracks, timeout=config["timeout"])
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
        items = web_client.get_one(f"me/top/{variant}").get("items", [])
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
