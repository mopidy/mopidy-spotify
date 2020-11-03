from unittest import mock

from mopidy import models

import spotify


def test_has_a_root_directory(provider):
    assert provider.root_directory == models.Ref.directory(
        uri="spotify:directory", name="Spotify"
    )


def test_browse_root_directory(provider):
    results = provider.browse("spotify:directory")

    assert len(results) == 3
    assert models.Ref.directory(uri="spotify:top", name="Top lists") in results
    assert (
        models.Ref.directory(uri="spotify:your", name="Your music") in results
    )
    assert (
        models.Ref.directory(uri="spotify:playlists", name="Playlists")
        in results
    )


def test_browse_top_lists_directory(provider):
    results = provider.browse("spotify:top")

    assert len(results) == 3
    assert (
        models.Ref.directory(uri="spotify:top:tracks", name="Top tracks")
        in results
    )
    assert (
        models.Ref.directory(uri="spotify:top:albums", name="Top albums")
        in results
    )
    assert (
        models.Ref.directory(uri="spotify:top:artists", name="Top artists")
        in results
    )


def test_browse_your_music_directory(provider):
    results = provider.browse("spotify:your")

    assert len(results) == 2
    assert (
        models.Ref.directory(uri="spotify:your:tracks", name="Your tracks")
        in results
    )
    assert (
        models.Ref.directory(uri="spotify:your:albums", name="Your albums")
        in results
    )


def test_browse_playlists_directory(provider):
    results = provider.browse("spotify:playlists")

    assert len(results) == 1
    assert (
        models.Ref.directory(uri="spotify:playlists:featured", name="Featured")
        in results
    )


def test_browse_playlist(web_client_mock, web_playlist_mock, provider):
    web_client_mock.get_playlist.return_value = web_playlist_mock

    results = provider.browse("spotify:user:alice:playlist:foo")

    web_client_mock.get_playlist.assert_called_once_with(
        "spotify:user:alice:playlist:foo"
    )
    assert len(results) == 1
    assert results[0] == models.Ref.track(
        uri="spotify:track:abc", name="ABC 123"
    )


def test_browse_album(
    session_mock, sp_album_mock, sp_album_browser_mock, sp_track_mock, provider
):
    session_mock.get_album.return_value = sp_album_mock
    sp_album_mock.browse.return_value = sp_album_browser_mock
    sp_album_browser_mock.tracks = [sp_track_mock, sp_track_mock]

    results = provider.browse("spotify:album:def")

    session_mock.get_album.assert_called_once_with("spotify:album:def")
    sp_album_mock.browse.assert_called_once_with()
    assert len(results) == 2
    assert results[0] == models.Ref.track(
        uri="spotify:track:abc", name="ABC 123"
    )


def test_browse_artist(
    session_mock,
    sp_artist_mock,
    sp_artist_browser_mock,
    sp_album_mock,
    sp_track_mock,
    provider,
):
    session_mock.get_artist.return_value = sp_artist_mock
    sp_artist_mock.browse.return_value = sp_artist_browser_mock
    sp_artist_browser_mock.albums = [sp_album_mock, sp_album_mock]
    sp_artist_browser_mock.tophit_tracks = [sp_track_mock, sp_track_mock]

    results = provider.browse("spotify:artist:abba")

    session_mock.get_artist.assert_called_once_with("spotify:artist:abba")
    sp_artist_mock.browse.assert_called_once_with(
        type=spotify.ArtistBrowserType.NO_TRACKS
    )
    assert len(results) == 4
    assert results[0] == models.Ref.track(
        uri="spotify:track:abc", name="ABC 123"
    )
    assert results[2] == models.Ref.album(
        uri="spotify:album:def", name="ABBA - DEF 456"
    )


def test_browse_toplist_when_offline(session_mock, provider):
    session_mock.connection.state = spotify.ConnectionState.OFFLINE
    toplist_mock = session_mock.get_toplist.return_value
    toplist_mock.is_loaded = False
    type(toplist_mock).tracks = mock.PropertyMock(side_effect=Exception)

    provider.browse("spotify:top:tracks:country")

    assert toplist_mock.load.call_count == 0


def test_browse_toplist_when_offline_web(web_client_mock, provider):
    web_client_mock.user_id = None

    results = provider.browse("spotify:top:tracks:user")

    assert len(results) == 0


def test_browse_top_tracks(provider):
    results = provider.browse("spotify:top:tracks")

    assert len(results) == 4
    assert (
        models.Ref.directory(uri="spotify:top:tracks:user", name="Personal")
        in results
    )
    assert (
        models.Ref.directory(uri="spotify:top:tracks:country", name="Country")
        in results
    )
    assert (
        models.Ref.directory(uri="spotify:top:tracks:everywhere", name="Global")
        in results
    )
    assert (
        models.Ref.directory(
            uri="spotify:top:tracks:countries", name="Other countries"
        )
        in results
    )


def test_browse_top_albums(provider):
    results = provider.browse("spotify:top:albums")

    assert len(results) == 3
    assert (
        models.Ref.directory(uri="spotify:top:albums:country", name="Country")
        in results
    )
    assert (
        models.Ref.directory(uri="spotify:top:albums:everywhere", name="Global")
        in results
    )
    assert (
        models.Ref.directory(
            uri="spotify:top:albums:countries", name="Other countries"
        )
        in results
    )


def test_browse_top_artists(provider):
    results = provider.browse("spotify:top:artists")

    assert len(results) == 4
    assert (
        models.Ref.directory(uri="spotify:top:artists:user", name="Personal")
        in results
    )
    assert (
        models.Ref.directory(uri="spotify:top:artists:country", name="Country")
        in results
    )
    assert (
        models.Ref.directory(
            uri="spotify:top:artists:everywhere", name="Global"
        )
        in results
    )
    assert (
        models.Ref.directory(
            uri="spotify:top:artists:countries", name="Other countries"
        )
        in results
    )


def test_browse_top_tracks_with_too_many_uri_parts(provider):
    results = provider.browse("spotify:top:tracks:foo:bar")

    assert len(results) == 0


def test_browse_unsupported_top_tracks(web_client_mock, provider):
    results = provider.browse("spotify:top:albums:user")

    web_client_mock.get_one.assert_not_called()
    assert len(results) == 0


def test_browse_personal_top_tracks_empty(web_client_mock, provider):
    web_client_mock.get_all.return_value = [{}]

    results = provider.browse("spotify:top:tracks:user")

    web_client_mock.get_all.assert_called_once_with(
        "me/top/tracks", params={"limit": 50}
    )
    assert len(results) == 0


def test_browse_personal_top_tracks(web_client_mock, web_track_mock, provider):
    # The tracks from this endpoint are erroneously missing some fields:
    del web_track_mock["is_playable"]
    web_client_mock.get_all.return_value = [
        {"items": [web_track_mock, web_track_mock]},
        {"items": [web_track_mock, web_track_mock]},
    ]

    results = provider.browse("spotify:top:tracks:user")

    web_client_mock.get_all.assert_called_once_with(
        "me/top/tracks", params={"limit": 50}
    )
    assert len(results) == 4
    assert results[0] == models.Ref.track(
        uri="spotify:track:abc", name="ABC 123"
    )


def test_browse_country_top_tracks(session_mock, sp_track_mock, provider):
    session_mock.user_country = "NO"
    session_mock.get_toplist.return_value.tracks = [
        sp_track_mock,
        sp_track_mock,
    ]

    results = provider.browse("spotify:top:tracks:country")

    session_mock.get_toplist.assert_called_once_with(
        type=spotify.ToplistType.TRACKS, region="NO"
    )
    assert len(results) == 2
    assert results[0] == models.Ref.track(
        uri="spotify:track:abc", name="ABC 123"
    )


def test_browse_global_top_tracks(session_mock, sp_track_mock, provider):
    session_mock.get_toplist.return_value.tracks = [
        sp_track_mock,
        sp_track_mock,
    ]

    results = provider.browse("spotify:top:tracks:everywhere")

    session_mock.get_toplist.assert_called_once_with(
        type=spotify.ToplistType.TRACKS, region=spotify.ToplistRegion.EVERYWHERE
    )
    assert len(results) == 2
    assert results[0] == models.Ref.track(
        uri="spotify:track:abc", name="ABC 123"
    )


def test_browse_top_track_countries_list_limited_by_config(
    session_mock, sp_track_mock, provider
):
    session_mock.get_toplist.return_value.tracks = [
        sp_track_mock,
        sp_track_mock,
    ]

    results = provider.browse("spotify:top:tracks:countries")

    assert len(results) == 2
    assert (
        models.Ref.directory(uri="spotify:top:tracks:gb", name="United Kingdom")
        in results
    )
    assert (
        models.Ref.directory(uri="spotify:top:tracks:us", name="United States")
        in results
    )


def test_browse_top_tracks_countries_unlimited_by_config(
    provider, backend_mock
):
    backend_mock._config["spotify"]["toplist_countries"] = []

    results = provider.browse("spotify:top:tracks:countries")

    assert len(results) > 50
    assert (
        models.Ref.directory(uri="spotify:top:tracks:no", name="Norway")
        in results
    )
    assert (
        models.Ref.directory(uri="spotify:top:tracks:gb", name="United Kingdom")
        in results
    )
    assert (
        models.Ref.directory(uri="spotify:top:tracks:us", name="United States")
        in results
    )


def test_browse_other_country_top_tracks(session_mock, sp_track_mock, provider):
    session_mock.get_toplist.return_value.tracks = [
        sp_track_mock,
        sp_track_mock,
    ]

    results = provider.browse("spotify:top:tracks:us")

    session_mock.get_toplist.assert_called_once_with(
        type=spotify.ToplistType.TRACKS, region="US"
    )
    assert len(results) == 2
    assert results[0] == models.Ref.track(
        uri="spotify:track:abc", name="ABC 123"
    )


def test_browse_unknown_country_top_tracks(
    session_mock, sp_track_mock, provider
):
    session_mock.get_toplist.return_value.tracks = [
        sp_track_mock,
        sp_track_mock,
    ]

    results = provider.browse("spotify:top:tracks:aa")

    session_mock.get_toplist.assert_called_once_with(
        type=spotify.ToplistType.TRACKS, region="AA"
    )
    assert len(results) == 2
    assert results[0] == models.Ref.track(
        uri="spotify:track:abc", name="ABC 123"
    )


def test_browse_top_albums_countries_list(
    session_mock, sp_track_mock, provider
):
    session_mock.get_toplist.return_value.tracks = [
        sp_track_mock,
        sp_track_mock,
    ]

    results = provider.browse("spotify:top:albums:countries")

    assert len(results) == 2
    assert (
        models.Ref.directory(uri="spotify:top:albums:gb", name="United Kingdom")
        in results
    )
    assert (
        models.Ref.directory(uri="spotify:top:albums:us", name="United States")
        in results
    )


def test_browse_personal_top_artists(
    web_client_mock, web_artist_mock, provider
):
    web_client_mock.get_all.return_value = [
        {"items": [web_artist_mock, web_artist_mock]},
        {"items": [web_artist_mock, web_artist_mock]},
    ]

    results = provider.browse("spotify:top:artists:user")

    web_client_mock.get_all.assert_called_once_with(
        "me/top/artists", params={"limit": 50}
    )
    assert len(results) == 4
    assert results[0] == models.Ref.artist(
        uri="spotify:artist:abba", name="ABBA"
    )


def test_browse_your_music_when_offline_web(web_client_mock, provider):
    web_client_mock.user_id = None

    results = provider.browse("spotify:your:tracks")

    assert len(results) == 0


def test_browse_your_music_unknown(provider):
    results = provider.browse("spotify:your:foobar")

    assert len(results) == 0


def test_browse_your_music_tracks_unknown(provider, caplog):
    results = provider.browse("spotify:your:tracks:foobar")

    assert len(results) == 0
    assert (
        "Failed to browse 'spotify:your:tracks:foobar': Unknown URI type"
        in caplog.text
    )


def test_browse_your_music_empty(web_client_mock, provider):
    web_client_mock.get_one.return_value = {}

    results = provider.browse("spotify:your:tracks")

    assert len(results) == 0


def test_browse_your_music_tracks(web_client_mock, web_track_mock, provider):
    web_saved_track_mock = {"track": web_track_mock}
    web_client_mock.get_all.return_value = [
        {"items": [web_saved_track_mock, web_saved_track_mock]},
        {"items": [web_saved_track_mock, web_saved_track_mock]},
    ]

    results = provider.browse("spotify:your:tracks")

    web_client_mock.get_all.assert_called_once_with(
        "me/tracks", params={"market": "from_token", "limit": 50}
    )
    assert results == [results[0]] * 4
    assert results[0] == models.Ref.track(
        uri="spotify:track:abc", name="ABC 123"
    )


def test_browse_your_music_albums(web_client_mock, web_album_mock, provider):
    web_saved_album_mock = {"album": web_album_mock}
    web_client_mock.get_all.return_value = [
        {"items": [web_saved_album_mock, web_saved_album_mock]},
        {"items": [web_saved_album_mock, web_saved_album_mock]},
    ]

    results = provider.browse("spotify:your:albums")

    web_client_mock.get_all.assert_called_once_with(
        "me/albums", params={"market": "from_token", "limit": 50}
    )
    assert results == [results[0]] * 4
    assert results[0] == models.Ref.album(
        uri="spotify:album:def", name="DEF 456"
    )


def test_browse_playlists_featured(
    web_client_mock, web_playlist_mock, provider
):
    web_client_mock.get_all.return_value = [
        {"playlists": {"items": [web_playlist_mock]}},
        {"playlists": {"items": [web_playlist_mock]}},
    ]

    results = provider.browse("spotify:playlists:featured")

    web_client_mock.get_all.assert_called_once_with(
        "browse/featured-playlists", params={"limit": 50}
    )

    assert len(results) == 2
    assert results[0].name == "Foo"
    assert results[0].uri == "spotify:user:alice:playlist:foo"
