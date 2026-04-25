from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mopidy import models
from mopidy.models import Track
from mopidy.types import Uri

from mopidy_spotify import browse, playlists, translator
from mopidy_spotify.utils import group_by_type
from mopidy_spotify.web import LinkType, WebLink

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

    from mopidy_spotify.types import SpotifyConfig
    from mopidy_spotify.web import SpotifyOAuthClient

logger = logging.getLogger(__name__)

_VARIOUS_ARTISTS_URI = "spotify:artist:0LyfQWJT6nXafLPZqxe9Of"

# Only for tracks and albums where the result doesn't change.
_cache: dict[tuple[LinkType, str | None], list[Track]] = {}


def lookup(
    config: SpotifyConfig,
    web_client: SpotifyOAuthClient,
    uris: Iterable[Uri],
) -> dict[Uri, list[Track]]:
    if not web_client.logged_in:
        logger.error("Not logged in")
        return {}

    result: dict[Uri, list[Track]] = {}
    links = (_parse_uri(u) for u in uris)
    for link_type, link_group in group_by_type(links):
        batch = []
        for link in link_group:
            key = _make_cache_key(link)
            if cached_tracks := _cache.get(key):
                result[Uri(link.uri)] = cached_tracks
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


def _make_cache_key(link: WebLink) -> tuple[LinkType, str | None]:
    return (link.type, link.id)


def _cache_tracks(
    link: WebLink | None,
    tracks: list[Track],
) -> tuple[LinkType, str | None] | None:
    if not tracks or not link:
        return None

    for t in tracks:
        if (parsed := _parse_uri(t.uri)) is None:
            continue
        track_key = _make_cache_key(parsed)
        _cache[track_key] = [t]

    if link.type not in (LinkType.TRACK, LinkType.ALBUM):
        return None
    key = _make_cache_key(link)
    _cache[key] = tracks
    return key


def _parse_uri(uri: Uri) -> WebLink | None:
    try:
        return WebLink.from_uri(uri)
    except ValueError as exc:
        logger.info(exc)
    return None


def _lookup_batch(
    config: SpotifyConfig,
    web_client: SpotifyOAuthClient,
    link_type: LinkType,
    links: list[WebLink],
) -> Generator[tuple[Uri, list[Track]]]:
    bitrate = config["bitrate"]
    for link, item in web_client.get_batch(link_type, links):
        results: list[Track] = []
        if link_type == LinkType.TRACK:
            if (track := translator.web_to_track(item, bitrate=bitrate)) is not None:
                results = [track]
            else:
                logger.info(f"Track '{link.uri}' not found")
        else:
            results = translator.web_to_album_tracks(item, bitrate=bitrate)
        _cache_tracks(link, results)
        yield Uri(link.uri), results


def _lookup_artist(
    config: SpotifyConfig,
    web_client: SpotifyOAuthClient,
    link: WebLink,
) -> dict[Uri, list[Track]]:
    results: list[Track] = []
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
        album_uri = web_album.get("uri")
        album_link = _parse_uri(album_uri) if album_uri else None
        _cache_tracks(album_link, album_tracks)
        results += album_tracks
    return {Uri(link.uri): results}


def _lookup_playlist(
    config: SpotifyConfig,
    web_client: SpotifyOAuthClient,
    link: WebLink,
) -> dict[Uri, list[Track]]:
    playlist = playlists.playlist_lookup(
        web_client,
        link.uri,
        bitrate=config["bitrate"],
    )
    if not isinstance(playlist, models.Playlist):
        logger.error(f"Playlist '{link.uri}' not found")
        return {}
    _cache_tracks(link, list(playlist.tracks))
    return {Uri(link.uri): list(playlist.tracks)}


def _lookup_your(
    config: SpotifyConfig,
    web_client: SpotifyOAuthClient,
    link: WebLink,
) -> dict[Uri, list[Track]]:
    parts = link.uri.replace("spotify:your:", "").split(":")
    if len(parts) != 1:
        logger.error(f"Your URI '{link.uri}' is not supported.")
        return {}
    variant = parts[0]
    if variant not in {"tracks", "albums"}:
        logger.error(f"Your type '{variant}' is not supported.")
        return {}

    results = list[Track]()
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
        album_uris = list[Uri]()
        for item in items:
            # The extra level here is to also support "saved album objects".
            web_album = item.get("album", item)
            if (album_ref := translator.web_to_album_ref(web_album)) is None:
                continue
            album_uris.append(Uri(album_ref.uri))
        album_results = lookup(config, web_client, album_uris)
        for u in album_uris:
            results += album_results.get(u, [])
    return {link.uri: results}
