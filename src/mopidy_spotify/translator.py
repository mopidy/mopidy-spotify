from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal, overload

from mopidy.models import Album, Artist, Image, Playlist, Ref, Track
from mopidy.types import DurationMs, Uri

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Mapping

    from mopidy.types import Query, SearchField

logger = logging.getLogger(__name__)


def web_to_artist_ref(web_artist: Mapping[str, Any]) -> Ref | None:
    if not valid_web_data(web_artist, "artist"):
        return None

    uri = web_artist["uri"]
    return Ref.artist(
        uri=Uri(uri),
        name=web_artist.get("name", uri),
    )


def web_to_artist_refs(
    web_artists: Iterable[Mapping[str, Any]],
) -> Generator[Ref]:
    for web_artist in web_artists:
        ref = web_to_artist_ref(web_artist)
        if ref is not None:
            yield ref


def web_to_album_ref(web_album: Mapping[str, Any]) -> Ref | None:
    if not valid_web_data(web_album, "album"):
        return None

    if "name" in web_album:
        artists = web_album.get("artists", [])
        if artists and artists[0].get("name"):
            name = f"{artists[0].get('name')} - {web_album['name']}"
        else:
            name = web_album["name"]
    else:
        name = web_album["uri"]

    return Ref.album(
        uri=Uri(web_album["uri"]),
        name=name,
    )


def web_to_album_refs(
    web_albums: Iterable[Mapping[str, Any]],
) -> Generator[Ref]:
    for web_album in web_albums:
        ref = web_to_album_ref(
            # The extra level here is to also support "saved album objects".
            web_album.get("album", web_album),
        )
        if ref is not None:
            yield ref


def valid_web_data(data: Any, object_type: str) -> bool:
    return (
        isinstance(data, dict)
        and data.get("type") == object_type
        and data.get("uri") is not None
    )


def web_to_track_ref(
    web_track: Mapping[str, Any],
    *,
    check_playable: bool = True,
) -> Ref | None:
    if not valid_web_data(web_track, "track"):
        return None

    # Web API track relinking guide says to use original URI.
    # libspotfy will handle any relinking when track is loaded for playback.
    uri = web_track.get("linked_from", {}).get("uri") or web_track["uri"]

    if check_playable and not web_track.get("is_playable", False):
        logger.debug(f"{uri!r} is not playable")
        return None

    return Ref.track(
        uri=Uri(uri),
        name=web_track.get("name", uri),
    )


def web_to_track_refs(
    web_tracks: Iterable[Mapping[str, Any]],
    *,
    check_playable: bool = True,
) -> Generator[Ref]:
    for web_track in web_tracks:
        ref = web_to_track_ref(
            # The extra level here is to also support "saved track objects".
            web_track.get("track", web_track),
            check_playable=check_playable,
        )
        if ref is not None:
            yield ref


@overload
def to_playlist(
    web_playlist: Mapping[str, Any],
    *,
    username: str | None = None,
    bitrate: int | None = None,
    as_ref: Literal[True],
    as_items: bool = False,
) -> Ref | None: ...


@overload
def to_playlist(
    web_playlist: Mapping[str, Any],
    *,
    username: str | None = None,
    bitrate: int | None = None,
    as_ref: Literal[False] = False,
    as_items: Literal[True],
) -> list[Ref] | None: ...


@overload
def to_playlist(
    web_playlist: Mapping[str, Any],
    *,
    username: str | None = None,
    bitrate: int | None = None,
    as_ref: Literal[False] = False,
    as_items: Literal[False] = False,
) -> Playlist | None: ...


def to_playlist(
    web_playlist: Mapping[str, Any],
    *,
    username: str | None = None,
    bitrate: int | None = None,
    as_ref: bool = False,
    as_items: bool = False,
) -> Ref | list[Ref] | Playlist | None:
    ref = to_playlist_ref(web_playlist, username)
    if ref is None or as_ref:
        return ref

    web_tracks = web_playlist.get("tracks", {}).get("items") or []
    if as_items and not isinstance(web_tracks, list):
        return None

    if as_items:
        return list(web_to_track_refs(web_tracks))

    tracks = [
        web_to_track(web_track.get("track", {}), bitrate=bitrate)
        for web_track in web_tracks
    ]
    tracks = [t for t in tracks if t]

    return Playlist(
        uri=ref.uri,
        name=ref.name,
        tracks=tuple(tracks),
    )


def to_playlist_ref(
    web_playlist: Mapping[str, Any],
    username: str | None = None,
) -> Ref | None:
    if not valid_web_data(web_playlist, "playlist"):
        return None

    name = web_playlist.get("name", web_playlist["uri"])

    owner = web_playlist.get("owner", {}).get("id", username)
    if username is not None and owner != username:
        name = f"{name} (by {owner})"

    return Ref.playlist(
        uri=Uri(web_playlist["uri"]),
        name=name,
    )


def to_playlist_refs(
    web_playlists: Iterable[Mapping[str, Any]],
    username: str | None = None,
) -> Generator[Ref]:
    for web_playlist in web_playlists:
        ref = to_playlist_ref(web_playlist, username)
        if ref is not None:
            yield ref


# Maps from Mopidy search query field to Spotify search query field.
# `None` if there is no matching concept.
SEARCH_FIELD_MAP = {
    "albumartist": "artist",
    "date": "year",
    "track_name": "track",
    "track_number": None,
}


def sp_search_query(
    query: Query[SearchField],
    *,
    exact: bool = False,
) -> str:
    """Translate a Mopidy search query to a Spotify search query"""

    result = []

    for field, values in query.items():
        field = SEARCH_FIELD_MAP.get(field, field)  # noqa: PLW2901
        if field is None:
            continue

        for value in values:
            if field == "year":
                value = _transform_year(value)  # noqa: PLW2901
                if value is not None:
                    result.append(f"{field}:{value}")
            elif field == "any":
                if exact:
                    result.append(f'"{value}"')
                else:
                    result.append(str(value))
            elif exact:
                result.append(f'{field}:"{value}"')
            else:
                words = str(value).split()
                result.append(" ".join(f"{field}:{word}" for word in words))

    return " ".join(result)


def _transform_year(date: Any) -> int | None:
    try:
        return int(str(date).split("-")[0])
    except ValueError:
        logger.debug(f'Excluded year from search query: Cannot parse date "{date}"')
        return None


def web_to_artist(web_artist: Mapping[str, Any]) -> Artist | None:
    ref = web_to_artist_ref(web_artist)
    if ref is None:
        return None
    return Artist(
        uri=ref.uri,
        name=ref.name,
    )


def web_to_album_tracks(
    web_album: Mapping[str, Any],
    bitrate: int | None = None,
) -> list[Track]:
    album = web_to_album(web_album)
    if album is None:
        return []

    if not web_album.get("is_playable", False):
        return []

    web_tracks = web_album.get("tracks", {}).get("items", [])
    if not isinstance(web_tracks, list):
        return []

    tracks = [web_to_track(web_track, bitrate, album) for web_track in web_tracks]
    return [t for t in tracks if t]


def web_to_album(web_album: Mapping[str, Any]) -> Album | None:
    ref = web_to_album_ref(web_album)
    if ref is None:
        return None

    artists = [web_to_artist(web_artist) for web_artist in web_album.get("artists", [])]
    artists = [a for a in artists if a]

    name = web_album.get("name", "Unknown album")
    return Album(
        uri=ref.uri,
        name=name,
        artists=frozenset(artists),
    )


def int_or_none(inp: Any) -> int | None:
    if inp is not None:
        return int(float(inp))
    return None


def web_to_track(
    web_track: Mapping[str, Any],
    bitrate: int | None = None,
    album: Album | None = None,
) -> Track | None:
    ref = web_to_track_ref(web_track)
    if ref is None:
        return None

    artists = [web_to_artist(web_artist) for web_artist in web_track.get("artists", [])]
    artists = [a for a in artists if a]

    if album is None:
        album = web_to_album(web_track.get("album", {}))

    duration_ms = int_or_none(web_track.get("duration_ms"))
    return Track(
        uri=ref.uri,
        name=ref.name,
        artists=frozenset(artists),
        album=album,
        length=DurationMs(duration_ms) if duration_ms is not None else None,
        disc_no=int_or_none(web_track.get("disc_number")),
        track_no=int_or_none(web_track.get("track_number")),
        bitrate=bitrate,
    )


def web_to_image(web_image: Mapping[str, Any]) -> Image:
    return Image(
        uri=web_image["url"],
        height=int_or_none(web_image.get("height")),
        width=int_or_none(web_image.get("width")),
    )
