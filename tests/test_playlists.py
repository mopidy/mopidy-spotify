from unittest import mock

import functools
import pytest
import re
from mopidy import backend as backend_api
from mopidy.models import Ref

import spotify
from mopidy_spotify import playlists

@pytest.fixture
def web_client_mock(web_client_mock, web_track_mock, web_album_mock, web_artist_mock, web_track_factory):
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
    web_playlist4 = {
        "owner": {"id": "alice"},
        "name": "Large",
        "tracks": {"items": [
            web_track_factory(f'id{i}') for i in range(500)
        ]},
        "uri": "spotify:user:alice:playlist:large",
        "type": "playlist",
    }
    web_playlists = [web_playlist1, web_playlist2, web_playlist3, web_playlist4]
    web_playlists_map = {x["uri"]: x for x in web_playlists}

    def get_user_playlists(*args, **kwargs):
        return list(web_playlists_map.values())

    def get_playlist(*args, **kwargs):
        return web_playlists_map.get(args[0], {})

    def _edit_playlist(method, playlist_uri, json):
        if method == 'put':
            if 'uris' in json:
                # replace all tracks with provided ones
                uris = json['uris']
                assert len(uris) <= 100
                web_playlists_map[playlist_uri]['tracks']['items'] = [web_track_factory(e.replace("spotify:track:", "")) for e in uris]
            else: 
                # reoder items
                insert_before = json['insert_before']
                range_start = json['range_start']
                range_length = json.get('range_length', 1)
                if insert_before < range_start: # move to front
                    web_playlists_map[playlist_uri]['tracks']['items'] = (
                        web_playlists_map[playlist_uri]['tracks']['items'][:insert_before] +
                        web_playlists_map[playlist_uri]['tracks']['items'][range_start:range_start+range_length] +
                        web_playlists_map[playlist_uri]['tracks']['items'][insert_before:range_start] +
                        web_playlists_map[playlist_uri]['tracks']['items'][range_start+range_length:]
                    )
                else: # move to back
                    web_playlists_map[playlist_uri]['tracks']['items'] = (
                        web_playlists_map[playlist_uri]['tracks']['items'][:range_start] +
                        web_playlists_map[playlist_uri]['tracks']['items'][range_start+range_length:insert_before] +
                        web_playlists_map[playlist_uri]['tracks']['items'][range_start:range_start+range_length] +
                        web_playlists_map[playlist_uri]['tracks']['items'][insert_before:]
                    )
        elif method == 'post':
            # add tracks to the given position
            uris = json['uris']
            assert len(uris) <= 100
            position = json.get('position', len(web_playlists_map[playlist_uri]['tracks']['items']))
            assert position >= 0  # prevent accidental 'from the right' indexing
            web_playlists_map[playlist_uri]['tracks']['items'] = (
                web_playlists_map[playlist_uri]['tracks']['items'][:position] +
                [web_track_factory(e.replace("spotify:track:", "")) for e in uris] +
                web_playlists_map[playlist_uri]['tracks']['items'][position:]
            )
        elif method == 'delete':
            # remove given tracks
            tracks = json['tracks'] # [ {uri:'spotify:track:<ID>', positions:[<int>,...], ... ]
            assert len(tracks) <= 100
            for track in sorted(tracks, key=lambda x: x['positions'][0], reverse=True):
                assert track['positions'][0] >= 0  # don't allow 'from the right' indexing
                assert web_playlists_map[playlist_uri]['tracks']['items'][track['positions'][0]]['track']['uri'] == track['uri']
                del web_playlists_map[playlist_uri]['tracks']['items'][track['positions'][0]]
        else:
            raise NotImplementedError

        return True

    def _create_playlist(method, json):
        playlist_id = f"spotify:user:alice:playlist:id{len(web_playlists_map)}"

        new_playlist = {
            "owner": {"id": "alice"},
            "name": json['name'],
            "tracks": {"items": []},
            "uri": playlist_id,
            "type": "playlist",
        }
        web_playlists_map[playlist_id] = new_playlist

        return True, playlist_id

    def _delete_playlist(method, playlist_id):
        playlist_id = "spotify:user:alice:playlist:"+playlist_id
        if playlist_id not in web_playlists_map:
            return False

        del web_playlists_map[playlist_id]
        return True


    def _rename_playlist(method, playlist_uri, json):
        assert 'name' in json
        web_playlists_map[playlist_uri]['name'] = json['name']


    web_client_mock._test_requests_history = []  # gets instanciated for each test_*()

    def request(method, path, *, json=None):
        method = method.lower()
        path_parts = path.split('/')
        web_client_mock._test_requests_history.append(method)
        if re.fullmatch(r"users/(.*?)/playlists/(.*?)/tracks", path):
            user_id, playlist_id = path_parts[1], path_parts[3]
            playlist_uri = f'spotify:user:{user_id}:playlist:{playlist_id}'
            rv = _edit_playlist(method, playlist_uri, json)
            return mock.Mock(status_ok=rv)
        elif re.fullmatch(r"users/(.*?)/playlists", path):
            user_id = path_parts[1]
            ok, playlist_id = _create_playlist(method, json)
            rv = mock.MagicMock(status_ok=ok)
            rv.__getitem__.return_value = playlist_id
            return rv
        elif re.fullmatch(r"playlists/(.*?)/followers", path):
            playlist_id = path_parts[1]
            rv = _delete_playlist(method, playlist_id)
            return mock.Mock(status_ok=rv)
        elif re.fullmatch(r"playlists/(.*?)", path):
            playlist_id = path_parts[1]
            playlist_uri = next((k for k in web_playlists_map.keys() if k.endswith(f':playlist:{playlist_id}')))
            _rename_playlist(method, playlist_uri, json)
            return mock.Mock(status_ok=True)
        else:
            raise NotImplementedError


    web_client_mock.get = functools.partial(request, 'get')
    web_client_mock.post = functools.partial(request, 'post')
    web_client_mock.put = functools.partial(request, 'put')
    web_client_mock.patch = functools.partial(request, 'patch')
    web_client_mock.delete = functools.partial(request, 'delete')

    web_client_mock.get_user_playlists.side_effect = get_user_playlists
    web_client_mock.get_playlist.side_effect = get_playlist
    return web_client_mock


@pytest.fixture
def provider(backend_mock, web_client_mock):
    backend_mock._web_client = web_client_mock
    playlists._sp_links.clear()
    provider = playlists.SpotifyPlaylistsProvider(backend_mock)
    provider._loaded = True
    provider._test_request_history = lambda: web_client_mock._test_requests_history
    return provider


def test_is_a_playlists_provider(provider):
    assert isinstance(provider, backend_api.PlaylistsProvider)


def test_as_list_when_not_logged_in(web_client_mock, provider):
    web_client_mock.logged_in = False

    result = provider.as_list()

    assert len(result) == 0


def test_as_list_when_offline(web_client_mock, provider):
    web_client_mock.get_user_playlists.side_effect = lambda: {}

    result = provider.as_list()

    assert len(result) == 0


def test_as_list_when_not_loaded(provider):
    provider._loaded = False

    result = provider.as_list()

    assert len(result) == 0


def test_as_list_when_playlist_wont_translate(provider):
    result = provider.as_list()

    assert len(result) == 3

    assert result[0] == Ref.playlist(
        uri="spotify:user:alice:playlist:foo", name="Foo"
    )
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
    assert web_client_mock.get_playlist.call_count == 3
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

    assert "Refreshed 3 Spotify playlists" in caplog.text


def test_refresh_clears_caches(provider, web_client_mock):
    playlists._sp_links = {"bar": "foobar"}

    provider.refresh()

    assert "bar" not in playlists._sp_links
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


@pytest.mark.parametrize("as_items", [(False), (True)])
def test_playlist_lookup_stores_track_link(
    session_mock,
    web_client_mock,
    sp_track_mock,
    web_playlist_mock,
    web_track_mock,
    as_items,
):
    session_mock.get_link.return_value = sp_track_mock.link
    web_playlist_mock["tracks"]["items"] = [{"track": web_track_mock}] * 5
    web_client_mock.get_playlist.return_value = web_playlist_mock
    playlists._sp_links.clear()

    playlists.playlist_lookup(
        session_mock,
        web_client_mock,
        "spotify:user:alice:playlist:foo",
        None,
        as_items,
    )

    session_mock.get_link.assert_called_once_with("spotify:track:abc")
    assert {"spotify:track:abc": sp_track_mock.link} == playlists._sp_links


@pytest.mark.parametrize(
    "connection_state",
    [
        (spotify.ConnectionState.OFFLINE),
        (spotify.ConnectionState.DISCONNECTED),
        (spotify.ConnectionState.LOGGED_OUT),
    ],
)
def test_playlist_lookup_when_not_logged_in(
    session_mock, web_client_mock, web_playlist_mock, connection_state
):
    web_client_mock.get_playlist.return_value = web_playlist_mock
    session_mock.connection.state = connection_state
    playlists._sp_links.clear()

    playlist = playlists.playlist_lookup(
        session_mock, web_client_mock, "spotify:user:alice:playlist:foo", None
    )

    assert playlist.uri == "spotify:user:alice:playlist:foo"
    assert playlist.name == "Foo"
    assert len(playlists._sp_links) == 0


def test_playlist_lookup_when_playlist_is_empty(
    session_mock, web_client_mock, caplog
):
    web_client_mock.get_playlist.return_value = {}
    playlists._sp_links.clear()

    playlist = playlists.playlist_lookup(
        session_mock, web_client_mock, "nothing", None
    )

    assert playlist is None
    assert "Failed to lookup Spotify playlist URI 'nothing'" in caplog.text
    assert len(playlists._sp_links) == 0


def test_playlist_lookup_when_link_invalid(
    session_mock, web_client_mock, web_playlist_mock, caplog
):
    session_mock.get_link.side_effect = ValueError("an error message")
    web_client_mock.get_playlist.return_value = web_playlist_mock
    playlists._sp_links.clear()

    playlist = playlists.playlist_lookup(
        session_mock, web_client_mock, "spotify:user:alice:playlist:foo", None
    )

    assert len(playlist.tracks) == 1
    assert "Failed to get link 'spotify:track:abc'" in caplog.text
