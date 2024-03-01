from unittest import mock

import pytest
from mopidy import backend as backend_api
from mopidy.models import Ref
from mopidy_spotify import playlists


@pytest.fixture()
def web_client_mock(web_client_mock, web_track_mock):
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

    def get_playlist(*args, **kwargs):
        return web_playlists_map.get(args[0], {})

    web_client_mock.get_user_playlists.return_value = web_playlists
    web_client_mock.get_playlist.side_effect = get_playlist
    return web_client_mock


@pytest.fixture()
def provider(backend_mock, web_client_mock):
    backend_mock._web_client = web_client_mock
    provider = playlists.SpotifyPlaylistsProvider(backend_mock)
    provider._loaded = True
    return provider


def test_is_a_playlists_provider(provider):
    assert isinstance(provider, backend_api.PlaylistsProvider)


def test_as_list_when_not_logged_in(web_client_mock, provider):
    web_client_mock.logged_in = False

    result = provider.as_list()

    assert len(result) == 0


def test_as_list_when_offline(web_client_mock, provider):
    web_client_mock.get_user_playlists.return_value = {}

    result = provider.as_list()

    assert len(result) == 0


def test_as_list_when_not_loaded(provider):
    provider._loaded = False

    result = provider.as_list()

    assert len(result) == 0


def test_as_list_when_playlist_wont_translate(provider):
    result = provider.as_list()

    assert len(result) == 2

    assert result[0] == Ref.playlist(uri="spotify:user:alice:playlist:foo", name="Foo")
    assert result[1] == Ref.playlist(
        uri="spotify:user:bob:playlist:baz", name="Baz (by bob)"
    )


def test_get_items_when_playlist_exists(provider):
    result = provider.get_items("spotify:user:alice:playlist:foo")

    assert len(result) == 1

    assert result[0] == Ref.track(uri="spotify:track:abc", name="ABC 123")


def test_get_items_when_playlist_without_tracks(provider):
    result = provider.get_items("spotify:user:bob:playlist:baz")

    assert len(result) == 0


def test_get_items_when_not_logged_in(web_client_mock, provider):
    web_client_mock.logged_in = False

    assert provider.get_items("spotify:user:alice:playlist:foo") is None


def test_get_items_when_offline(web_client_mock, provider, caplog):
    web_client_mock.get_playlist.side_effect = None
    web_client_mock.get_playlist.return_value = {}

    assert provider.get_items("spotify:user:alice:playlist:foo") is None
    assert (
        "Failed to lookup Spotify playlist URI "
        "'spotify:user:alice:playlist:foo'" in caplog.text
    )


def test_get_items_when_not_loaded(provider):
    provider._loaded = False

    result = provider.get_items("spotify:user:alice:playlist:foo")

    assert len(result) == 1
    assert result[0] == Ref.track(uri="spotify:track:abc", name="ABC 123")


def test_get_items_when_playlist_wont_translate(provider):
    assert provider.get_items("spotify:user:alice:playlist:malformed") is None


def test_get_items_when_playlist_is_unknown(provider, caplog):
    assert provider.get_items("spotify:user:alice:playlist:unknown") is None
    assert (
        "Failed to lookup Spotify playlist URI "
        "'spotify:user:alice:playlist:unknown'" in caplog.text
    )


def test_refresh_loads_all_playlists(provider, web_client_mock):
    provider.refresh()

    web_client_mock.get_user_playlists.assert_called_once()
    assert web_client_mock.get_playlist.call_count == 2
    expected_calls = [
        mock.call("spotify:user:alice:playlist:foo"),
        mock.call("spotify:user:bob:playlist:baz"),
    ]
    web_client_mock.get_playlist.assert_has_calls(expected_calls)


def test_refresh_when_not_logged_in(provider, web_client_mock):
    provider._loaded = False
    web_client_mock.logged_in = False

    provider.refresh()

    web_client_mock.get_user_playlists.assert_not_called()
    web_client_mock.get_playlist.assert_not_called()
    assert not provider._loaded


def test_refresh_sets_loaded(provider, web_client_mock):
    provider._loaded = False

    provider.refresh()

    web_client_mock.get_user_playlists.assert_called_once()
    web_client_mock.get_playlist.assert_called()
    assert provider._loaded


def test_refresh_counts_playlists(provider, caplog):
    provider.refresh()

    assert "Refreshed 2 Spotify playlists" in caplog.text


def test_refresh_clears_caches(provider, web_client_mock):
    provider.refresh()

    web_client_mock.clear_cache.assert_called_once()


def test_lookup(provider):
    playlist = provider.lookup("spotify:user:alice:playlist:foo")

    assert playlist.uri == "spotify:user:alice:playlist:foo"
    assert playlist.name == "Foo"
    assert playlist.tracks[0].bitrate == 160


def test_lookup_when_not_logged_in(web_client_mock, provider):
    web_client_mock.logged_in = False

    playlist = provider.lookup("spotify:user:alice:playlist:foo")

    assert playlist is None


def test_lookup_when_not_loaded(provider):
    provider._loaded = False

    playlist = provider.lookup("spotify:user:alice:playlist:foo")

    assert playlist.uri == "spotify:user:alice:playlist:foo"
    assert playlist.name == "Foo"


def test_lookup_when_playlist_is_empty(provider, caplog):
    assert provider.lookup("nothing") is None
    assert "Failed to lookup Spotify playlist URI 'nothing'" in caplog.text


def test_lookup_of_playlist_with_other_owner(provider):
    playlist = provider.lookup("spotify:user:bob:playlist:baz")

    assert playlist.uri == "spotify:user:bob:playlist:baz"
    assert playlist.name == "Baz (by bob)"


def test_playlist_lookup_when_link_invalid(web_client_mock, web_playlist_mock, caplog):
    web_client_mock.get_playlist.return_value = web_playlist_mock

    playlist = playlists.playlist_lookup(
        web_client_mock,
        "spotify:in:valid",
        bitrate=None,
    )

    assert playlist is None
    assert "Failed to lookup Spotify playlist URI 'spotify:in:valid'" in caplog.text
