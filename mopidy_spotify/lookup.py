import logging

import spotify
from mopidy_spotify import playlists, translator, utils, web

logger = logging.getLogger(__name__)

_VARIOUS_ARTISTS_URIS = [
    "spotify:artist:0LyfQWJT6nXafLPZqxe9Of",
]


def lookup(config, session, web_client, uri):
    try:
        web_link = web.WebLink.from_uri(uri)
        if web_link.type != web.LinkType.PLAYLIST:
            sp_link = session.get_link(uri)
    except ValueError as exc:
        logger.info(f"Failed to lookup {uri!r}: {exc}")
        return []

    try:
        if web_link.type == web.LinkType.PLAYLIST:
            return _lookup_playlist(config, session, web_client, uri)
        elif sp_link.type is spotify.LinkType.TRACK:
            return list(_lookup_track(config, sp_link))
        elif sp_link.type is spotify.LinkType.ALBUM:
            return list(_lookup_album(config, sp_link))
        elif sp_link.type is spotify.LinkType.ARTIST:
            with utils.time_logger("Artist lookup"):
                return list(_lookup_artist(config, sp_link))
        else:
            logger.info(
                f"Failed to lookup {uri!r}: Cannot handle {sp_link.type!r}"
            )
            return []
    except spotify.Error as exc:
        logger.info(f"Failed to lookup {uri!r}: {exc}")
        return []


def _lookup_track(config, sp_link):
    sp_track = sp_link.as_track()
    sp_track.load(config["timeout"])
    track = translator.to_track(sp_track, bitrate=config["bitrate"])
    if track is not None:
        yield track


def _lookup_album(config, sp_link):
    sp_album = sp_link.as_album()
    sp_album_browser = sp_album.browse()
    sp_album_browser.load(config["timeout"])
    for sp_track in sp_album_browser.tracks:
        track = translator.to_track(sp_track, bitrate=config["bitrate"])
        if track is not None:
            yield track


def _lookup_artist(config, sp_link):
    sp_artist = sp_link.as_artist()
    sp_artist_browser = sp_artist.browse(
        type=spotify.ArtistBrowserType.NO_TRACKS
    )
    sp_artist_browser.load(config["timeout"])

    # Get all album browsers we need first, so they can start retrieving
    # data in the background.
    sp_album_browsers = []
    for sp_album in sp_artist_browser.albums:
        sp_album.load(config["timeout"])
        if not sp_album.is_available:
            continue
        if sp_album.type is spotify.AlbumType.COMPILATION:
            continue
        if sp_album.artist.link.uri in _VARIOUS_ARTISTS_URIS:
            continue
        sp_album_browsers.append(sp_album.browse())

    for sp_album_browser in sp_album_browsers:
        sp_album_browser.load(config["timeout"])
        for sp_track in sp_album_browser.tracks:
            track = translator.to_track(sp_track, bitrate=config["bitrate"])
            if track is not None:
                yield track


def _lookup_playlist(config, session, web_client, uri):
    playlist = playlists.playlist_lookup(
        session, web_client, uri, config["bitrate"]
    )
    if playlist is None:
        raise spotify.Error("Playlist Web API lookup failed")
    return playlist.tracks
