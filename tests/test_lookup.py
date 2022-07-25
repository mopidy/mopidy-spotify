import copy


def test_lookup_of_invalid_uri(provider, caplog):
    results = provider.lookup("invalid")

    assert len(results) == 0
    assert "Failed to lookup 'invalid': Could not parse" in caplog.text


def test_lookup_of_invalid_playlist_uri(provider, caplog):
    results = provider.lookup("spotify:playlist")

    assert len(results) == 0
    assert "Failed to lookup 'spotify:playlist': Could not parse" in caplog.text


def test_lookup_of_invalid_track_uri(web_client_mock, provider, caplog):
    web_client_mock.get_track.return_value = {}

    results = provider.lookup("spotify:track:invalid")

    assert len(results) == 0
    assert (
        "Failed to lookup Spotify track 'spotify:track:invalid': Invalid track response"
        in caplog.text
    )


def test_lookup_of_unhandled_uri(provider, caplog):
    results = provider.lookup("spotify:invalid:something")

    assert len(results) == 0
    assert (
        "Failed to lookup 'spotify:invalid:something': "
        "Could not parse 'spotify:invalid:something' as a Spotify URI"
        in caplog.text
    )


def test_lookup_when_offline(web_client_mock, provider, caplog):
    web_client_mock.logged_in = False

    results = provider.lookup("spotify:invalid:something")

    assert len(results) == 0
    assert "Failed to lookup" not in caplog.text


def test_lookup_of_track_uri(web_client_mock, web_track_mock, provider):
    web_client_mock.get_track.return_value = web_track_mock

    results = provider.lookup("spotify:track:abc")

    assert len(results) == 1
    track = results[0]
    assert track.uri == "spotify:track:abc"
    assert track.name == "ABC 123"
    assert track.bitrate == 160
    assert track.album.name == "DEF 456"


def test_lookup_of_album_uri(web_client_mock, web_album_mock, provider):
    web_client_mock.get_album.return_value = web_album_mock

    results = provider.lookup("spotify:album:def")

    assert len(results) == 10
    track = results[0]
    assert track.uri == "spotify:track:abc"
    assert track.name == "ABC 123"
    assert track.bitrate == 160
    assert track.album.name == "DEF 456"


def test_lookup_of_artist_uri(
    web_track_mock, web_album_mock, web_client_mock, provider
):
    web_track_mock2 = copy.deepcopy(web_track_mock)
    web_track_mock2["name"] = "XYZ track"
    web_album_mock2 = copy.deepcopy(web_album_mock)
    web_album_mock2["name"] = "XYZ album"
    web_album_mock2["tracks"]["items"] = [web_track_mock2] * 3

    web_client_mock.get_artist_albums.return_value = [
        web_album_mock,
        web_album_mock2,
    ]
    results = provider.lookup("spotify:artist:abba")

    assert len(results) == 13

    track = results[0]
    assert track.uri == "spotify:track:abc"
    assert track.name == "ABC 123"
    assert track.album.name == "DEF 456"
    assert track.bitrate == 160

    track = results[10]
    assert track.uri == "spotify:track:abc"
    assert track.name == "XYZ track"
    assert track.album.name == "XYZ album"
    assert track.bitrate == 160


def test_lookup_of_artist_ignores_unavailable_albums(
    web_client_mock, web_album_mock, web_album_mock2, provider
):
    web_album_mock["is_playable"] = False
    web_client_mock.get_artist_albums.return_value = [
        web_album_mock,
        web_album_mock2,
    ]

    results = provider.lookup("spotify:artist:abba")

    assert len(results) == 2


def test_lookup_of_artist_uri_ignores_compilations(
    web_client_mock, web_album_mock, provider
):
    web_album_mock["album_type"] = "compilation"
    web_client_mock.get_artist_albums.return_value = [web_album_mock]

    results = provider.lookup("spotify:artist:abba")

    assert len(results) == 0


def test_lookup_of_artist_uri_ignores_various_artists_albums(
    web_client_mock, web_album_mock, provider
):
    web_album_mock["artists"][0][
        "uri"
    ] = "spotify:artist:0LyfQWJT6nXafLPZqxe9Of"
    web_client_mock.get_artist_albums.return_value = [web_album_mock]

    results = provider.lookup("spotify:artist:abba")

    assert len(results) == 0


def test_lookup_of_playlist_uri(web_client_mock, web_playlist_mock, provider):
    web_client_mock.get_playlist.return_value = web_playlist_mock

    results = provider.lookup("spotify:playlist:alice:foo")

    web_client_mock.get_playlist.assert_called_once_with(
        "spotify:playlist:alice:foo"
    )

    assert len(results) == 1
    track = results[0]
    assert track.uri == "spotify:track:abc"
    assert track.name == "ABC 123"
    assert track.bitrate == 160


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
        assert track.album.name == "DEF 456"


def test_lookup_of_youralbums_uri(web_client_mock, web_album_mock, provider):
    web_saved_album_mock = {"album": web_album_mock}
    web_client_mock.get_all.return_value = [
        {"items": [web_saved_album_mock, web_saved_album_mock]},
        {"items": [web_saved_album_mock, web_saved_album_mock]},
    ]
    web_client_mock.get_album.return_value = web_album_mock

    results = provider.lookup("spotify:your:albums")

    assert len(results) == 4 * 10
    for track in results:
        assert track.uri == "spotify:track:abc"
        assert track.name == "ABC 123"
        assert track.album.uri == "spotify:album:def"
        assert track.bitrate == 160
        assert track.album.name == "DEF 456"


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
