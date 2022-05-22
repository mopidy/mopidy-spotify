import logging

import spotify
from mopidy_spotify import browse, playlists, translator, utils
from mopidy_spotify.web import LinkType, WebLink

logger = logging.getLogger(__name__)

_VARIOUS_ARTISTS_URIS = [
    "spotify:artist:0LyfQWJT6nXafLPZqxe9Of",
]


def lookup(config, session, web_client, uri):
    if web_client is None or not web_client.logged_in:
        return []

    try:
        web_link = WebLink.from_uri(uri)
    except ValueError as exc:
        logger.info(f"Failed to lookup {uri!r}: {exc}")
        return []

    try:
        if web_link.type == LinkType.PLAYLIST:
            return _lookup_playlist(config, web_client, uri)
        elif web_link.type == LinkType.YOUR:
            return list(_lookup_your(config, session, web_client, uri))
        elif web_link.type == LinkType.TRACK:
            return list(_lookup_track(config, web_client, uri))
        elif web_link.type == LinkType.ALBUM:
            return list(_lookup_album(config, sp_link))
        elif web_link.type == LinkType.ARTIST:
            with utils.time_logger("Artist lookup"):
                return list(_lookup_artist(config, sp_link))
        else:
            logger.info(
                f"Failed to lookup {uri!r}: Cannot handle {web_link.type!r}"
            )
            return []
    except spotify.Error as exc:
        logger.info(f"Failed to lookup {uri!r}: {exc}")
        return []


def _lookup_track(config, web_client, uri):
    web_track = web_client.get_track(uri)

    if web_track == {}:
        logger.error(f"Failed to lookup Spotify track URI {uri!r}")
        return

    track = translator.web_to_track(web_track, bitrate=config["bitrate"])
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


def _lookup_playlist(config, web_client, uri):
    playlist = playlists.playlist_lookup(web_client, uri, config["bitrate"])
    if playlist is None:
        raise spotify.Error("Playlist Web API lookup failed")
    return playlist.tracks


def _lookup_your(config, session, web_client, uri):
    parts = uri.replace("spotify:your:", "").split(":")
    if len(parts) != 1:
        return
    variant = parts[0]

    items = browse._load_your_music(web_client, variant)
    if variant == "tracks":
        for item in items:
            # The extra level here is to also support "saved track objects".
            web_track = item.get("track", item)
            track = translator.web_to_track(
                web_track, bitrate=config["bitrate"]
            )
            if track is not None:
                yield track
    elif variant == "albums":
        for item in items:
            # The extra level here is to also support "saved album objects".
            web_album = item.get("album", item)
            album_ref = translator.web_to_album_ref(web_album)
            if album_ref is None:
                continue
            sp_link = session.get_link(album_ref.uri)
            if sp_link.type is spotify.LinkType.ALBUM:
                yield from _lookup_album(config, sp_link)
