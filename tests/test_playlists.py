import logging
from typing import Any
from unittest import mock

import pytest
from mopidy import backend as backend_api
from mopidy.core import CoreListener
from mopidy.models import Ref
from mopidy.types import Uri

from mopidy_spotify import playlists
from tests import ThreadJoiner


@pytest.fixture
def web_client_mock(
    web_client_mock: mock.MagicMock, web_track_mock: dict[str, Any]
) -> mock.MagicMock:
    web_playlist1 = {
        "owner": {"id": "alice"},
        "name": "Foo",
        "tracks": {"items": [{"track": web_track_mock}]},
        "uri": "spotify:user:alice:playlist:foo",
        "type": "playlist",
    }
    web_playlist2 = {
        "owner": {"id": "bob"},
        "name": "Baz",
        "uri": "spotify:user:bob:playlist:baz",
        "type": "playlist",
    }
    web_playlist3 = {
        "owner": {"id": "alice"},
        "name": "Malformed",
        "tracks": {"items": []},
        "uri": "spotify:user:alice:playlist:malformed",
        "type": "bogus",
    }
    web_playlists = [web_playlist1, web_playlist2, web_playlist3]
    web_playlists_map = {x["uri"]: x for x in web_playlists}

    def get_playlist(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return web_playlists_map.get(args[0], {})

    web_client_mock.get_user_playlists.return_value = web_playlists
    web_client_mock.get_playlist.side_effect = get_playlist
    return web_client_mock


@pytest.fixture
def provider(
    backend_mock: mock.Mock, web_client_mock: mock.MagicMock
) -> playlists.SpotifyPlaylistsProvider:
    backend_mock._web_client = web_client_mock
    return playlists.SpotifyPlaylistsProvider(backend_mock)


def test_is_a_playlists_provider(provider: playlists.SpotifyPlaylistsProvider):
    assert isinstance(provider, backend_api.PlaylistsProvider)


def test_as_list_when_not_logged_in(
    web_client_mock: mock.MagicMock, provider: playlists.SpotifyPlaylistsProvider
):
    web_client_mock.logged_in = False

    result = provider.as_list()

    assert len(result) == 0


def test_as_list_when_offline(
    web_client_mock: mock.MagicMock, provider: playlists.SpotifyPlaylistsProvider
):
    web_client_mock.get_user_playlists.return_value = {}

    result = provider.as_list()

    assert len(result) == 0


def test_as_list_when_playlist_wont_translate(
    provider: playlists.SpotifyPlaylistsProvider,
):
    result = provider.as_list()

    assert len(result) == 2

    assert result[0] == Ref.playlist(
        uri=Uri("spotify:user:alice:playlist:foo"), name="Foo"
    )
    assert result[1] == Ref.playlist(
        uri=Uri("spotify:user:bob:playlist:baz"), name="Baz (by bob)"
    )


def test_get_items_when_playlist_exists(provider: playlists.SpotifyPlaylistsProvider):
    result = provider.get_items(Uri("spotify:user:alice:playlist:foo"))

    assert len(result) == 1

    assert result[0] == Ref.track(uri=Uri("spotify:track:abc"), name="ABC 123")


def test_get_items_when_playlist_without_tracks(
    provider: playlists.SpotifyPlaylistsProvider,
):
    result = provider.get_items(Uri("spotify:user:bob:playlist:baz"))

    assert len(result) == 0


def test_get_items_when_not_logged_in(
    web_client_mock: mock.MagicMock, provider: playlists.SpotifyPlaylistsProvider
):
    web_client_mock.logged_in = False

    assert provider.get_items(Uri("spotify:user:alice:playlist:foo")) is None


def test_get_items_when_offline(
    web_client_mock: mock.MagicMock,
    provider: playlists.SpotifyPlaylistsProvider,
    caplog: pytest.LogCaptureFixture,
):
    web_client_mock.get_playlist.side_effect = None
    web_client_mock.get_playlist.return_value = {}

    assert provider.get_items(Uri("spotify:user:alice:playlist:foo")) is None
    assert (
        "Failed to lookup Spotify playlist URI "
        "'spotify:user:alice:playlist:foo'" in caplog.text
    )


def test_get_items_when_playlist_wont_translate(
    provider: playlists.SpotifyPlaylistsProvider,
):
    assert provider.get_items(Uri("spotify:user:alice:playlist:malformed")) is None


def test_get_items_when_playlist_is_unknown(
    provider: playlists.SpotifyPlaylistsProvider, caplog: pytest.LogCaptureFixture
):
    assert provider.get_items(Uri("spotify:user:alice:playlist:unknown")) is None
    assert (
        "Failed to lookup Spotify playlist URI "
        "'spotify:user:alice:playlist:unknown'" in caplog.text
    )


def test_refresh_loads_all_playlists(
    provider: playlists.SpotifyPlaylistsProvider, web_client_mock: mock.MagicMock
):
    with ThreadJoiner():
        provider.refresh()

    web_client_mock.get_user_playlists.assert_called_once()
    assert web_client_mock.get_playlist.call_count == 2
    expected_calls = [
        mock.call("spotify:user:alice:playlist:foo"),
        mock.call("spotify:user:bob:playlist:baz"),
    ]
    web_client_mock.get_playlist.assert_has_calls(expected_calls)


def test_refresh_when_not_logged_in(
    provider: playlists.SpotifyPlaylistsProvider, web_client_mock: mock.MagicMock
):
    web_client_mock.logged_in = False

    with ThreadJoiner():
        provider.refresh()

    web_client_mock.get_user_playlists.assert_not_called()
    web_client_mock.get_playlist.assert_not_called()


def test_refresh_in_progress(
    provider: playlists.SpotifyPlaylistsProvider,
    web_client_mock: mock.MagicMock,
    caplog: pytest.LogCaptureFixture,
):
    assert provider._refresh_mutex.acquire(blocking=False)

    with ThreadJoiner():
        provider.refresh()

    web_client_mock.get_user_playlists.assert_not_called()
    web_client_mock.get_playlist.assert_not_called()
    assert provider._refresh_mutex.locked()
    assert "Refreshing Spotify playlists already in progress" in caplog.text


def test_refresh_counts_valid_playlists(
    provider: playlists.SpotifyPlaylistsProvider, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.INFO)  # To avoid log corruption from debug logging.
    with ThreadJoiner():
        provider.refresh()

    assert "Refreshing 2 Spotify playlists in background" in caplog.text
    assert "Refreshed 2 Spotify playlists" in caplog.text


@mock.patch.object(CoreListener, "send")
def test_refresh_triggers_playlists_loaded_event(
    send: mock.MagicMock, provider: playlists.SpotifyPlaylistsProvider
):
    with ThreadJoiner():
        provider.refresh()

    send.assert_called_once_with("playlists_loaded")


def test_refresh_with_refresh_true_arg(
    provider: playlists.SpotifyPlaylistsProvider, web_client_mock: mock.MagicMock
):
    with ThreadJoiner():
        provider.refresh()

    web_client_mock.get_user_playlists.assert_called_once_with(refresh=True)


def test_refresh_handles_error(
    provider: playlists.SpotifyPlaylistsProvider,
    web_client_mock: mock.MagicMock,
    caplog: pytest.LogCaptureFixture,
):
    web_client_mock.get_user_playlists.side_effect = Exception()

    with ThreadJoiner():
        provider.refresh()

    assert "Error occurred while refreshing Spotify playlists" in caplog.text
    assert not provider._refresh_mutex.locked()


def test_refresh_tracks_handles_error(
    provider: playlists.SpotifyPlaylistsProvider,
    web_client_mock: mock.MagicMock,
    caplog: pytest.LogCaptureFixture,
):
    web_client_mock.get_playlist.side_effect = Exception()

    with ThreadJoiner():
        provider.refresh()

    assert "Error occurred while refreshing Spotify playlists tracks" in caplog.text
    assert not provider._refresh_mutex.locked()


def test_refresh_tracks_needs_lock(
    provider: playlists.SpotifyPlaylistsProvider,
    web_client_mock: mock.MagicMock,
    caplog: pytest.LogCaptureFixture,
):
    assert provider._refresh_tracks("foo") == []

    assert "Lock must be held before calling this method" in caplog.text
    web_client_mock.get_playlist.assert_not_called()


def test_refresh_tracks(
    provider: playlists.SpotifyPlaylistsProvider,
    web_client_mock: mock.MagicMock,
    caplog: pytest.LogCaptureFixture,
):
    uris = ["spotify:user:alice:playlist:foo", "spotify:user:bob:playlist:baz"]

    assert provider._refresh_mutex.acquire(blocking=False)
    assert provider._refresh_tracks(uris) == uris

    expected_calls = [
        mock.call("spotify:user:alice:playlist:foo"),
        mock.call("spotify:user:bob:playlist:baz"),
    ]
    web_client_mock.get_playlist.assert_has_calls(expected_calls)


def test_lookup(provider: playlists.SpotifyPlaylistsProvider):
    playlist = provider.lookup(Uri("spotify:user:alice:playlist:foo"))

    assert playlist.uri == "spotify:user:alice:playlist:foo"
    assert playlist.name == "Foo"
    assert playlist.tracks[0].bitrate == 160


def test_lookup_when_not_logged_in(
    web_client_mock: mock.MagicMock, provider: playlists.SpotifyPlaylistsProvider
):
    web_client_mock.logged_in = False

    playlist = provider.lookup(Uri("spotify:user:alice:playlist:foo"))

    assert playlist is None


def test_lookup_when_playlist_is_empty(
    provider: playlists.SpotifyPlaylistsProvider, caplog: pytest.LogCaptureFixture
):
    assert provider.lookup(Uri("nothing")) is None
    assert "Failed to lookup Spotify playlist URI 'nothing'" in caplog.text


def test_lookup_of_playlist_with_other_owner(
    provider: playlists.SpotifyPlaylistsProvider,
):
    playlist = provider.lookup(Uri("spotify:user:bob:playlist:baz"))

    assert playlist.uri == "spotify:user:bob:playlist:baz"
    assert playlist.name == "Baz (by bob)"


def test_playlist_lookup_when_link_invalid(
    web_client_mock: mock.MagicMock,
    web_playlist_mock: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
):
    web_client_mock.get_playlist.return_value = web_playlist_mock

    playlist = playlists.playlist_lookup(
        web_client_mock,
        Uri("spotify:in:valid"),
        bitrate=None,
    )

    assert playlist is None
    assert "Failed to lookup Spotify playlist URI 'spotify:in:valid'" in caplog.text
