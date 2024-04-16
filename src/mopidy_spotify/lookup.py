import logging

from mopidy_spotify import browse, playlists, translator
from mopidy_spotify.utils import group_by_type
from mopidy_spotify.web import LinkType, WebLink

logger = logging.getLogger(__name__)

_VARIOUS_ARTISTS_URI = "spotify:artist:0LyfQWJT6nXafLPZqxe9Of"

# Only for tracks and albums where the result doesn't change.
_cache = {}  # (type, id) -> [Track(), ...]


def lookup(
    config,
    web_client,
    uris,
):
    if web_client is None or not web_client.logged_in:
        logger.error("Not logged in")
        return {}

    result = {}
    links = (_parse_uri(u) for u in uris)
    for link_type, link_group in group_by_type(links):
        batch = []
        for link in link_group:
            key = _make_cache_key(link)
            if cached_tracks := _cache.get(key):
                result[link.uri] = cached_tracks
            elif link_type == LinkType.PLAYLIST:
                result.update(_lookup_playlist(config, web_client, link))
            elif link_type == LinkType.YOUR:
                result.update(_lookup_your(config, web_client, link))
            elif link_type == LinkType.ARTIST:
                result.update(_lookup_artist(config, web_client, link))
            elif link_type in (LinkType.TRACK, LinkType.ALBUM):
                batch.append(link)
            else:
                logger.error(f"Cannot lookup {link_type!r} uri(s)")
                break
        if batch:
            result.update(_lookup_batch(config, web_client, link_type, batch))
    return result


def _make_cache_key(link):
    return (link.type, link.id)


def _cache_tracks(link, tracks):
    if not tracks or not link:
        return None

    for t in tracks:
        track_key = _make_cache_key(_parse_uri(t.uri))
        _cache[track_key] = [t]

    if link.type not in (LinkType.TRACK, LinkType.ALBUM):
        return None
    key = _make_cache_key(link)
    _cache[key] = tracks
    return key


def _parse_uri(uri):
    try:
        return WebLink.from_uri(uri)
    except ValueError as exc:
        logger.info(exc)
    return None


def _lookup_batch(config, web_client, link_type, links):
    bitrate = config["bitrate"]
    for link, item in web_client.get_batch(link_type, links):
        results = []
        if link_type == LinkType.TRACK:
            if (track := translator.web_to_track(item, bitrate=bitrate)) is not None:
                results = [track]
            else:
                logger.info(f"Track '{link.uri}' not found")
        else:
            results = translator.web_to_album_tracks(item, bitrate=bitrate)
        _cache_tracks(link, results)
        yield link.uri, results


def _lookup_artist(config, web_client, link):
    results = []
    for web_album in web_client.get_artist_albums(link):
        is_various_artists = False
        if web_album.get("album_type", "") == "compilation":
            continue
        for artist in web_album.get("artists", []):
            if artist.get("uri") == _VARIOUS_ARTISTS_URI:
                is_various_artists = True
                break
        if is_various_artists:
            continue
        album_tracks = translator.web_to_album_tracks(
            web_album, bitrate=config["bitrate"]
        )
        album_link = _parse_uri(web_album.get("uri"))
        _cache_tracks(album_link, album_tracks)
        results += album_tracks
    return {link.uri: results}


def _lookup_playlist(config, web_client, link):
    playlist = playlists.playlist_lookup(
        web_client,
        link.uri,
        bitrate=config["bitrate"],
    )
    if playlist is None:
        logger.error(f"Playlist '{link.uri}' not found")
        return {}
    _cache_tracks(link, playlist.tracks)
    return {link.uri: playlist.tracks}


def _lookup_your(config, web_client, link):
    parts = link.uri.replace("spotify:your:", "").split(":")
    if len(parts) != 1:
        logger.error(f"Your URI '{link.uri}' is not supported.")
        return {}
    variant = parts[0]
    if variant not in {"tracks", "albums"}:
        logger.error(f"Your type '{variant}' is not supported.")
        return {}

    results = []
    items = browse._load_your_music(web_client, variant)
    if variant == "tracks":
        for item in items:
            # The extra level here is to also support "saved track objects".
            web_track = item.get("track", item)
            track = translator.web_to_track(web_track, bitrate=config["bitrate"])
            if track is not None:
                _cache_tracks(_parse_uri(track.uri), [track])
                results.append(track)
    elif variant == "albums":
        album_uris = []
        for item in items:
            # The extra level here is to also support "saved album objects".
            web_album = item.get("album", item)
            if (album_ref := translator.web_to_album_ref(web_album)) is None:
                continue
            album_uris.append(album_ref.uri)
        album_results = lookup(config, web_client, album_uris)
        for u in album_uris:
            results += album_results.get(u, [])
    return {link.uri: results}
