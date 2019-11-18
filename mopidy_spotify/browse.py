import logging

import spotify

from mopidy import models
from mopidy_spotify import countries, translator

logger = logging.getLogger(__name__)

ROOT_DIR = models.Ref.directory(uri="spotify:directory", name="Spotify")

_ROOT_DIR_CONTENTS = [
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
    "user": lambda session: spotify.ToplistRegion.USER,
    "country": lambda session: session.user_country,
    "everywhere": lambda session: spotify.ToplistRegion.EVERYWHERE,
}


def browse(config, session, uri):
    if uri == ROOT_DIR.uri:
        return _ROOT_DIR_CONTENTS
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
            return _browse_toplist(
                config, session, variant=parts[0], region=parts[1]
            )
        else:
            logger.info(f'Failed to browse "{uri}": Toplist URI parsing failed')
            return []
    else:
        logger.info(f'Failed to browse "{uri}": Unknown URI type')
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
    return [
        models.Ref.directory(
            uri=f"spotify:top:{variant}:user", name="Personal"
        ),
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

    if region in ("user", "country", "everywhere"):
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
