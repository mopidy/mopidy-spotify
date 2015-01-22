from __future__ import unicode_literals

import mock

from mopidy import backend as backend_api, models

import pytest

import spotify

from mopidy_spotify import backend, library


@pytest.fixture
def session_mock():
    sp_session_mock = mock.Mock(spec=spotify.Session)
    return sp_session_mock


@pytest.fixture
def backend_mock(session_mock, config):
    backend_mock = mock.Mock(spec=backend.SpotifyBackend)
    backend_mock._config = config
    backend_mock._session = session_mock
    backend_mock._bitrate = 160
    return backend_mock


@pytest.fixture
def provider(backend_mock):
    return library.SpotifyLibraryProvider(backend_mock)


def test_is_a_playlists_provider(provider):
    assert isinstance(provider, backend_api.LibraryProvider)


def test_has_a_root_directory(provider):
    assert provider.root_directory == models.Ref.directory(
        uri='spotify:directory', name='Spotify')


def test_browse_root_directory(provider):
    results = provider.browse('spotify:directory')

    assert len(results) == 3
    assert models.Ref.directory(
        uri='spotify:top:tracks', name='Top tracks') in results
    assert models.Ref.directory(
        uri='spotify:top:albums', name='Top albums') in results
    assert models.Ref.directory(
        uri='spotify:top:artists', name='Top artists') in results


def test_browse_album(
        session_mock, sp_album_mock, sp_album_browser_mock, sp_track_mock,
        provider):
    session_mock.get_album.return_value = sp_album_mock
    sp_album_mock.browse.return_value = sp_album_browser_mock
    sp_album_browser_mock.tracks = [sp_track_mock, sp_track_mock]

    results = provider.browse('spotify:album:def')

    session_mock.get_album.assert_called_once_with('spotify:album:def')
    sp_album_mock.browse.assert_called_once_with()
    assert len(results) == 2
    assert results[0] == models.Ref.track(
        uri='spotify:track:abc', name='ABC 123')


def test_browse_artist(
        session_mock, sp_artist_mock, sp_artist_browser_mock,
        sp_album_mock, sp_track_mock, provider):
    session_mock.get_artist.return_value = sp_artist_mock
    sp_artist_mock.browse.return_value = sp_artist_browser_mock
    sp_artist_browser_mock.albums = [sp_album_mock, sp_album_mock]
    sp_artist_browser_mock.tophit_tracks = [sp_track_mock, sp_track_mock]

    results = provider.browse('spotify:artist:abba')

    session_mock.get_artist.assert_called_once_with('spotify:artist:abba')
    sp_artist_mock.browse.assert_called_once_with(
        type=spotify.ArtistBrowserType.NO_TRACKS)
    assert len(results) == 4
    assert results[0] == models.Ref.track(
        uri='spotify:track:abc', name='ABC 123')
    assert results[2] == models.Ref.album(
        uri='spotify:album:def', name='ABBA - DEF 456')


def test_browse_top_tracks(provider):
    results = provider.browse('spotify:top:tracks')

    assert len(results) == 4
    assert models.Ref.directory(
        uri='spotify:top:tracks:user', name='Personal') in results
    assert models.Ref.directory(
        uri='spotify:top:tracks:country', name='Country') in results
    assert models.Ref.directory(
        uri='spotify:top:tracks:everywhere', name='Global') in results
    assert models.Ref.directory(
        uri='spotify:top:tracks:countries', name='Other countries') in results


def test_browse_top_albums(provider):
    results = provider.browse('spotify:top:albums')

    assert len(results) == 4
    assert models.Ref.directory(
        uri='spotify:top:albums:user', name='Personal') in results
    assert models.Ref.directory(
        uri='spotify:top:albums:country', name='Country') in results
    assert models.Ref.directory(
        uri='spotify:top:albums:everywhere', name='Global') in results
    assert models.Ref.directory(
        uri='spotify:top:albums:countries', name='Other countries') in results


def test_browse_top_artists(provider):
    results = provider.browse('spotify:top:artists')

    assert len(results) == 4
    assert models.Ref.directory(
        uri='spotify:top:artists:user', name='Personal') in results
    assert models.Ref.directory(
        uri='spotify:top:artists:country', name='Country') in results
    assert models.Ref.directory(
        uri='spotify:top:artists:everywhere', name='Global') in results
    assert models.Ref.directory(
        uri='spotify:top:artists:countries', name='Other countries') in results


def test_browse_top_tracks_has_no_countries_when_configured_off(
        backend_mock):
    backend_mock._config['spotify']['toplist_countries'] = []

    results = provider(backend_mock).browse('spotify:top:tracks')

    assert models.Ref.directory(
        uri='spotify:top:tracks:countries',
        name='Other countries') not in results


def test_browse_top_tracks_with_too_many_uri_parts(provider):
    results = provider.browse('spotify:top:tracks:foo:bar')

    assert len(results) == 0


def test_browse_personal_top_tracks(session_mock, sp_track_mock, provider):
    session_mock.get_toplist.return_value.tracks = [
        sp_track_mock, sp_track_mock]

    results = provider.browse('spotify:top:tracks:user')

    session_mock.get_toplist.assert_called_once_with(
        type=spotify.ToplistType.TRACKS, region=spotify.ToplistRegion.USER)
    assert len(results) == 2
    assert results[0] == models.Ref.track(
        uri='spotify:track:abc', name='ABC 123')


def test_browse_country_top_tracks(session_mock, sp_track_mock, provider):
    session_mock.user_country = 'NO'
    session_mock.get_toplist.return_value.tracks = [
        sp_track_mock, sp_track_mock]

    results = provider.browse('spotify:top:tracks:country')

    session_mock.get_toplist.assert_called_once_with(
        type=spotify.ToplistType.TRACKS, region='NO')
    assert len(results) == 2
    assert results[0] == models.Ref.track(
        uri='spotify:track:abc', name='ABC 123')


def test_browse_global_top_tracks(session_mock, sp_track_mock, provider):
    session_mock.get_toplist.return_value.tracks = [
        sp_track_mock, sp_track_mock]

    results = provider.browse('spotify:top:tracks:everywhere')

    session_mock.get_toplist.assert_called_once_with(
        type=spotify.ToplistType.TRACKS,
        region=spotify.ToplistRegion.EVERYWHERE)
    assert len(results) == 2
    assert results[0] == models.Ref.track(
        uri='spotify:track:abc', name='ABC 123')


def test_browse_top_track_countries_list(
        session_mock, sp_track_mock, provider):
    session_mock.get_toplist.return_value.tracks = [
        sp_track_mock, sp_track_mock]

    results = provider.browse('spotify:top:tracks:countries')

    assert len(results) == 2
    assert models.Ref.directory(
        uri='spotify:top:tracks:gb', name='United Kingdom') in results
    assert models.Ref.directory(
        uri='spotify:top:tracks:us', name='United States') in results


def test_browse_other_country_top_tracks(
        session_mock, sp_track_mock, provider):
    session_mock.get_toplist.return_value.tracks = [
        sp_track_mock, sp_track_mock]

    results = provider.browse('spotify:top:tracks:us')

    session_mock.get_toplist.assert_called_once_with(
        type=spotify.ToplistType.TRACKS, region='US')
    assert len(results) == 2
    assert results[0] == models.Ref.track(
        uri='spotify:track:abc', name='ABC 123')


def test_browse_personal_top_albums(session_mock, sp_album_mock, provider):
    session_mock.get_toplist.return_value.albums = [
        sp_album_mock, sp_album_mock]

    results = provider.browse('spotify:top:albums:user')

    session_mock.get_toplist.assert_called_once_with(
        type=spotify.ToplistType.ALBUMS, region=spotify.ToplistRegion.USER)
    assert len(results) == 2
    assert results[0] == models.Ref.album(
        uri='spotify:album:def', name='ABBA - DEF 456')


def test_browse_personal_top_artists(session_mock, sp_artist_mock, provider):
    session_mock.get_toplist.return_value.artists = [
        sp_artist_mock, sp_artist_mock]

    results = provider.browse('spotify:top:artists:user')

    session_mock.get_toplist.assert_called_once_with(
        type=spotify.ToplistType.ARTISTS, region=spotify.ToplistRegion.USER)
    assert len(results) == 2
    assert results[0] == models.Ref.artist(
        uri='spotify:artist:abba', name='ABBA')


def test_lookup_of_invalid_uri(session_mock, provider, caplog):
    session_mock.get_link.side_effect = ValueError('an error message')

    results = provider.lookup('invalid')

    assert len(results) == 0
    assert 'Failed to lookup "invalid": an error message' in caplog.text()


def test_lookup_of_unhandled_uri(session_mock, provider, caplog):
    sp_link_mock = mock.Mock(spec=spotify.Link)
    sp_link_mock.type = spotify.LinkType.INVALID
    session_mock.get_link.return_value = sp_link_mock

    results = provider.lookup('something')

    assert len(results) == 0
    assert (
        'Failed to lookup "something": Cannot handle <LinkType.INVALID: 0>'
        in caplog.text())


def test_lookup_when_offline(session_mock, sp_track_mock, provider, caplog):
    session_mock.get_link.return_value = sp_track_mock.link
    sp_track_mock.link.as_track.return_value.load.side_effect = RuntimeError(
        'Must be online to load objects')

    results = provider.lookup('spotify:track:abc')

    assert len(results) == 0
    assert (
        'Failed to lookup "spotify:track:abc": Must be online to load objects'
        in caplog.text())


def test_lookup_of_track_uri(session_mock, sp_track_mock, provider):
    session_mock.get_link.return_value = sp_track_mock.link

    results = provider.lookup('spotify:track:abc')

    session_mock.get_link.assert_called_once_with('spotify:track:abc')
    sp_track_mock.link.as_track.assert_called_once_with()
    sp_track_mock.load.assert_called_once_with()

    assert len(results) == 1
    track = results[0]
    assert track.uri == 'spotify:track:abc'
    assert track.name == 'ABC 123'
    assert track.bitrate == 160


def test_lookup_of_album_uri(session_mock, sp_album_browser_mock, provider):
    sp_album_mock = sp_album_browser_mock.album
    session_mock.get_link.return_value = sp_album_mock.link

    results = provider.lookup('spotify:album:def')

    session_mock.get_link.assert_called_once_with('spotify:album:def')
    sp_album_mock.link.as_album.assert_called_once_with()

    sp_album_mock.browse.assert_called_once_with()
    sp_album_browser_mock.load.assert_called_once_with()

    assert len(results) == 2
    track = results[0]
    assert track.uri == 'spotify:track:abc'
    assert track.name == 'ABC 123'
    assert track.bitrate == 160


def test_lookup_of_artist_uri(
        session_mock, sp_artist_browser_mock, sp_album_browser_mock, provider):
    sp_artist_mock = sp_artist_browser_mock.artist
    sp_album_mock = sp_album_browser_mock.album
    session_mock.get_link.return_value = sp_artist_mock.link

    results = provider.lookup('spotify:artist:abba')

    session_mock.get_link.assert_called_once_with('spotify:artist:abba')
    sp_artist_mock.link.as_artist.assert_called_once_with()

    sp_artist_mock.browse.assert_called_once_with(
        type=spotify.ArtistBrowserType.NO_TRACKS)
    sp_artist_browser_mock.load.assert_called_once_with()

    assert sp_album_mock.browse.call_count == 2
    assert sp_album_browser_mock.load.call_count == 2

    assert len(results) == 4
    track = results[0]
    assert track.uri == 'spotify:track:abc'
    assert track.name == 'ABC 123'
    assert track.bitrate == 160


def test_lookup_of_artist_uri_ignores_compilations(
        session_mock, sp_artist_browser_mock, sp_album_browser_mock, provider):
    sp_artist_mock = sp_artist_browser_mock.artist
    session_mock.get_link.return_value = sp_artist_mock.link
    sp_album_mock = sp_album_browser_mock.album
    sp_album_mock.type = spotify.AlbumType.COMPILATION

    results = provider.lookup('spotify:artist:abba')

    assert len(results) == 0


def test_lookup_of_artist_uri_ignores_various_artists_albums(
        session_mock, sp_artist_browser_mock, sp_album_browser_mock, provider):
    sp_artist_mock = sp_artist_browser_mock.artist
    session_mock.get_link.return_value = sp_artist_mock.link
    sp_album_browser_mock.album.artist.link.uri = (
        'spotify:artist:0LyfQWJT6nXafLPZqxe9Of')

    results = provider.lookup('spotify:artist:abba')

    assert len(results) == 0


def test_lookup_of_playlist_uri(session_mock, sp_playlist_mock, provider):
    session_mock.get_link.return_value = sp_playlist_mock.link

    results = provider.lookup('spotify:playlist:alice:foo')

    session_mock.get_link.assert_called_once_with('spotify:playlist:alice:foo')
    sp_playlist_mock.link.as_playlist.assert_called_once_with()
    sp_playlist_mock.load.assert_called_once_with()

    assert len(results) == 1
    track = results[0]
    assert track.uri == 'spotify:track:abc'
    assert track.name == 'ABC 123'
    assert track.bitrate == 160


def test_search_with_no_query_returns_nothing(provider, caplog):
    result = provider.search()

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search'
    assert len(result.tracks) == 0
    assert 'Ignored search without query' in caplog.text()


def test_search_with_empty_query_returns_nothing(provider, caplog):
    result = provider.search({'any': []})

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search'
    assert len(result.tracks) == 0
    assert 'Ignored search with empty query' in caplog.text()


def test_search_by_single_uri(session_mock, sp_track_mock, provider):
    session_mock.get_link.return_value = sp_track_mock.link

    result = provider.search({'uri': ['spotify:track:abc']})

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:track:abc'
    assert len(result.tracks) == 1
    track = result.tracks[0]
    assert track.uri == 'spotify:track:abc'
    assert track.name == 'ABC 123'
    assert track.bitrate == 160


def test_search_by_multiple_uris(session_mock, sp_track_mock, provider):
    session_mock.get_link.return_value = sp_track_mock.link

    result = provider.search({
        'uri': ['spotify:track:abc', 'spotify:track:abc']
    })

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search'
    assert len(result.tracks) == 2
    track = result.tracks[0]
    assert track.uri == 'spotify:track:abc'
    assert track.name == 'ABC 123'
    assert track.bitrate == 160


def test_search_when_offline_returns_nothing(provider, caplog):
    provider._backend._online.is_set.return_value = False

    result = provider.search({'any': ['ABBA']})

    assert 'Search aborted: Spotify is offline' in caplog.text()

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search:%22ABBA%22'
    assert len(result.tracks) == 0


def test_search_returns_albums_and_artists_and_tracks(
        session_mock, sp_search_mock, provider, caplog):
    session_mock.search.return_value = sp_search_mock

    result = provider.search({'any': ['ABBA']})

    session_mock.search.assert_called_once_with(
        '"ABBA"', album_count=20, artist_count=10, track_count=50)
    sp_search_mock.load.assert_called_once_with()

    assert 'Searching Spotify for: "ABBA"' in caplog.text()

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search:%22ABBA%22'

    assert len(result.albums) == 1
    assert result.albums[0].uri == 'spotify:album:def'

    assert len(result.artists) == 1
    assert result.artists[0].uri == 'spotify:artist:abba'

    assert len(result.tracks) == 2
    assert result.tracks[0].uri == 'spotify:track:abc'


def test_find_exact_is_the_same_as_search(provider):
    assert provider.find_exact == provider.search
