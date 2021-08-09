from unittest import mock

import spotify


def test_lookup_of_invalid_uri(provider, caplog):
    results = provider.lookup("invalid")

    assert len(results) == 0
    assert "Failed to lookup 'invalid': Could not parse" in caplog.text


def test_lookup_of_invalid_playlist_uri(provider, caplog):
    results = provider.lookup("spotify:playlist")

    assert len(results) == 0
    assert "Failed to lookup 'spotify:playlist': Could not parse" in caplog.text


def test_lookup_of_invalid_track_uri(session_mock, provider, caplog):
    session_mock.get_link.side_effect = ValueError("an error message")

    results = provider.lookup("spotify:track:invalid")

    assert len(results) == 0
    assert (
        "Failed to lookup 'spotify:track:invalid': an error message"
        in caplog.text
    )


def test_lookup_of_unhandled_uri(session_mock, provider, caplog):
    sp_link_mock = mock.Mock(spec=spotify.Link)
    sp_link_mock.type = spotify.LinkType.INVALID
    session_mock.get_link.return_value = sp_link_mock

    results = provider.lookup("spotify:artist:something")

    assert len(results) == 0
    assert (
        "Failed to lookup 'spotify:artist:something': "
        "Cannot handle <LinkType.INVALID: 0>" in caplog.text
    )


def test_lookup_when_offline(session_mock, sp_track_mock, provider, caplog):
    session_mock.get_link.return_value = sp_track_mock.link
    sp_track_mock.link.as_track.return_value.load.side_effect = spotify.Error(
        "Must be online to load objects"
    )

    results = provider.lookup("spotify:track:abc")

    assert len(results) == 0
    assert (
        "Failed to lookup 'spotify:track:abc': Must be online to load objects"
        in caplog.text
    )


def test_lookup_of_track_uri(session_mock, sp_track_mock, provider):
    session_mock.get_link.return_value = sp_track_mock.link

    results = provider.lookup("spotify:track:abc")

    session_mock.get_link.assert_called_once_with("spotify:track:abc")
    sp_track_mock.link.as_track.assert_called_once_with()
    sp_track_mock.load.assert_called_once_with(10)

    assert len(results) == 1
    track = results[0]
    assert track.uri == "spotify:track:abc"
    assert track.name == "ABC 123"
    assert track.bitrate == 160


def test_lookup_of_album_uri(session_mock, sp_album_browser_mock, provider):
    sp_album_mock = sp_album_browser_mock.album
    session_mock.get_link.return_value = sp_album_mock.link

    results = provider.lookup("spotify:album:def")

    session_mock.get_link.assert_called_once_with("spotify:album:def")
    sp_album_mock.link.as_album.assert_called_once_with()

    sp_album_mock.browse.assert_called_once_with()
    sp_album_browser_mock.load.assert_called_once_with(10)

    assert len(results) == 2
    track = results[0]
    assert track.uri == "spotify:track:abc"
    assert track.name == "ABC 123"
    assert track.bitrate == 160


def test_lookup_of_artist_uri(
    session_mock, sp_artist_browser_mock, sp_album_browser_mock, provider
):
    sp_artist_mock = sp_artist_browser_mock.artist
    sp_album_mock = sp_album_browser_mock.album
    session_mock.get_link.return_value = sp_artist_mock.link

    results = provider.lookup("spotify:artist:abba")

    session_mock.get_link.assert_called_once_with("spotify:artist:abba")
    sp_artist_mock.link.as_artist.assert_called_once_with()

    sp_artist_mock.browse.assert_called_once_with(
        type=spotify.ArtistBrowserType.NO_TRACKS
    )
    sp_artist_browser_mock.load.assert_called_once_with(10)

    assert sp_album_mock.browse.call_count == 2
    assert sp_album_browser_mock.load.call_count == 2

    assert len(results) == 4
    track = results[0]
    assert track.uri == "spotify:track:abc"
    assert track.name == "ABC 123"
    assert track.bitrate == 160


def test_lookup_of_artist_ignores_unavailable_albums(
    session_mock, sp_artist_browser_mock, sp_album_browser_mock, provider
):
    sp_artist_mock = sp_artist_browser_mock.artist
    session_mock.get_link.return_value = sp_artist_mock.link
    sp_album_mock = sp_album_browser_mock.album
    sp_album_mock.is_available = False

    results = provider.lookup("spotify:artist:abba")

    assert len(results) == 0


def test_lookup_of_artist_uri_ignores_compilations(
    session_mock, sp_artist_browser_mock, sp_album_browser_mock, provider
):
    sp_artist_mock = sp_artist_browser_mock.artist
    session_mock.get_link.return_value = sp_artist_mock.link
    sp_album_mock = sp_album_browser_mock.album
    sp_album_mock.type = spotify.AlbumType.COMPILATION

    results = provider.lookup("spotify:artist:abba")

    assert len(results) == 0


def test_lookup_of_artist_uri_ignores_various_artists_albums(
    session_mock, sp_artist_browser_mock, sp_album_browser_mock, provider
):
    sp_artist_mock = sp_artist_browser_mock.artist
    session_mock.get_link.return_value = sp_artist_mock.link
    sp_album_browser_mock.album.artist.link.uri = (
        "spotify:artist:0LyfQWJT6nXafLPZqxe9Of"
    )

    results = provider.lookup("spotify:artist:abba")

    assert len(results) == 0


def test_lookup_of_playlist_uri(
    session_mock, web_client_mock, web_playlist_mock, sp_track_mock, provider
):
    web_client_mock.get_playlist.return_value = web_playlist_mock
    session_mock.get_link.return_value = sp_track_mock.link

    results = provider.lookup("spotify:playlist:alice:foo")

    session_mock.get_link.assert_called_once_with("spotify:track:abc")
    web_client_mock.get_playlist.assert_called_once_with(
        "spotify:playlist:alice:foo"
    )

    assert len(results) == 1
    track = results[0]
    assert track.uri == "spotify:track:abc"
    assert track.name == "ABC 123"
    assert track.bitrate == 160


def test_lookup_of_playlist_uri_when_not_logged_in(
    web_client_mock, provider, caplog
):
    web_client_mock.user_id = None

    results = provider.lookup("spotify:playlist:alice:foo")

    assert len(results) == 0
    assert (
        "Failed to lookup 'spotify:playlist:alice:foo': "
        "Playlist Web API lookup failed" in caplog.text
    )


def test_lookup_of_yourtracks_uri(web_client_mock, web_track_mock, provider):
    web_saved_track_mock = {"track": web_track_mock}
    web_client_mock.get_all.return_value = [
        {"items": [web_saved_track_mock, web_saved_track_mock]},
        {"items": [web_saved_track_mock, web_saved_track_mock]},
    ]

    results = provider.lookup("spotify:your:tracks")

    assert len(results) == 4
    for track in results:
        assert track.uri == "spotify:track:abc"
        assert track.name == "ABC 123"
        assert track.bitrate == 160


def test_lookup_of_youralbums_uri(
    session_mock,
    web_client_mock,
    web_album_mock,
    sp_album_browser_mock,
    provider,
):
    web_saved_album_mock = {"album": web_album_mock}
    web_client_mock.get_all.return_value = [
        {"items": [web_saved_album_mock, web_saved_album_mock]},
        {"items": [web_saved_album_mock, web_saved_album_mock]},
    ]

    sp_album_mock = sp_album_browser_mock.album
    session_mock.get_link.return_value = sp_album_mock.link

    results = provider.lookup("spotify:your:albums")

    get_link_call = mock.call("spotify:album:def")
    assert session_mock.get_link.call_args_list == [
        get_link_call,
        get_link_call,
        get_link_call,
        get_link_call,
    ]
    assert sp_album_mock.link.as_album.call_count == 4

    assert sp_album_mock.browse.call_count == 4
    load_call = mock.call(10)
    assert sp_album_browser_mock.load.call_args_list == [
        load_call,
        load_call,
        load_call,
        load_call,
    ]

    assert len(results) == 8
    for track in results:
        assert track.uri == "spotify:track:abc"
        assert track.name == "ABC 123"
        assert track.album.uri == "spotify:album:def"
        assert track.bitrate == 160


def test_lookup_of_your_uri_when_not_logged_in(web_client_mock, provider):
    web_client_mock.user_id = None

    results = provider.lookup("spotify:your:tracks")

    assert len(results) == 0


def test_lookup_of_unhandled_your_uri(provider):
    results = provider.lookup("spotify:your:artists")

    assert len(results) == 0


def test_lookup_of_invalid_your_uri(provider, caplog):
    results = provider.lookup("spotify:your:tracks:invalid")

    assert len(results) == 0
    assert (
        "Failed to lookup 'spotify:your:tracks:invalid': Could not parse"
        in caplog.text
    )
