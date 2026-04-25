from typing import TypedDict


class SpotifyConfig(TypedDict):
    enabled: bool
    client_id: str
    client_secret: str
    bitrate: int
    volume_normalization: bool
    timeout: int
    allow_cache: bool
    cache_size: int
    allow_playlists: bool
    search_album_count: int
    search_artist_count: int
    search_track_count: int
