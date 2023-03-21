import logging

from mopidy_spotify import browse, playlists, translator, utils
from mopidy_spotify.web import LinkType, WebLink, WebError

logger = logging.getLogger(__name__)

_VARIOUS_ARTISTS_URI = "spotify:artist:0LyfQWJT6nXafLPZqxe9Of"


def lookup(config, web_client, uri):
    if web_client is None or not web_client.logged_in:
        return []

    try:
        link = WebLink.from_uri(uri)
    except ValueError as exc:
        logger.info(f"Failed to lookup {uri!r}: {exc}")
        return []

    try:
        if link.type == LinkType.PLAYLIST:
            return _lookup_playlist(config, web_client, link)
        elif link.type == LinkType.YOUR:
            return list(_lookup_your(config, web_client, link))
        elif link.type == LinkType.TRACK:
            return list(_lookup_track(config, web_client, link))
        elif link.type == LinkType.ALBUM:
            return list(_lookup_album(config, web_client, link))
        elif link.type == LinkType.ARTIST:
            with utils.time_logger("Artist lookup"):
                return list(_lookup_artist(config, web_client, link))
        else:
            logger.info(
                f"Failed to lookup {uri!r}: Cannot handle {link.type!r}"
            )
            return []
    except WebError as exc:
        logger.info(
            f"Failed to lookup Spotify {link.type.value} {link.uri!r}: {exc}"
        )
        return []


def _lookup_track(config, web_client, link):
    web_track = web_client.get_track(link)

    if web_track == {}:
        raise WebError("Invalid track response")

    track = translator.web_to_track(web_track, bitrate=config["bitrate"])
    if track is not None:
        yield track


def _lookup_album(config, web_client, link):
    web_album = web_client.get_album(link)
    if web_album == {}:
        raise WebError("Invalid album response")

    yield from translator.web_to_album_tracks(
        web_album, bitrate=config["bitrate"]
    )


def _lookup_artist(config, web_client, link):
    web_albums = web_client.get_artist_albums(link)
    for web_album in web_albums:
        is_various_artists = False
        if web_album.get("album_type", "") == "compilation":
            continue
        for artist in web_album.get("artists", []):
            if artist.get("uri") == _VARIOUS_ARTISTS_URI:
                is_various_artists = True
                break
        if is_various_artists:
            continue
        yield from translator.web_to_album_tracks(
            web_album, bitrate=config["bitrate"]
        )


def _lookup_playlist(config, web_client, link):
    playlist = playlists.playlist_lookup(
        web_client, link.uri, config["bitrate"]
    )
    if playlist is None:
        raise WebError("Invalid playlist response")
    return playlist.tracks


def _lookup_your(config, web_client, link):
    parts = link.uri.replace("spotify:your:", "").split(":")
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
            web_link = WebLink.from_uri(album_ref.uri)
            if web_link.type == LinkType.ALBUM:
                yield from _lookup_album(config, web_client, web_link)
