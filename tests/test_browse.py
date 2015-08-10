from __future__ import unicode_literals

import mock

from mopidy import models

import spotify

from . import conftest


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


def test_browse_playlist(
        session_mock, sp_playlist_mock, sp_track_mock, provider):
    session_mock.get_playlist.return_value = sp_playlist_mock
    sp_playlist_mock.tracks = [sp_track_mock, sp_track_mock]

    results = provider.browse('spotify:user:alice:playlist:foo')

    session_mock.get_playlist.assert_called_once_with(
        'spotify:user:alice:playlist:foo')
    assert len(results) == 2
    assert results[0] == models.Ref.track(
        uri='spotify:track:abc', name='ABC 123')


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


def test_browse_toplist_when_offline(session_mock, provider):
    session_mock.connection.state = spotify.ConnectionState.OFFLINE
    toplist_mock = session_mock.get_toplist.return_value
    toplist_mock.is_loaded = False
    type(toplist_mock).tracks = mock.PropertyMock(side_effect=Exception)

    provider.browse('spotify:top:tracks:user')

    assert toplist_mock.load.call_count == 0


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


def test_browse_top_track_countries_list_limited_by_config(
        session_mock, sp_track_mock, provider):
    session_mock.get_toplist.return_value.tracks = [
        sp_track_mock, sp_track_mock]

    results = provider.browse('spotify:top:tracks:countries')

    assert len(results) == 2
    assert models.Ref.directory(
        uri='spotify:top:tracks:gb', name='United Kingdom') in results
    assert models.Ref.directory(
        uri='spotify:top:tracks:us', name='United States') in results


def test_browse_top_tracks_countries_unlimited_by_config(
        backend_mock):
    backend_mock._config['spotify']['toplist_countries'] = []
    provider = conftest.provider(backend_mock)

    results = provider.browse('spotify:top:tracks:countries')

    assert len(results) > 50
    assert models.Ref.directory(
        uri='spotify:top:tracks:no', name='Norway') in results
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


def test_browse_unknown_country_top_tracks(
        session_mock, sp_track_mock, provider):
    session_mock.get_toplist.return_value.tracks = [
        sp_track_mock, sp_track_mock]

    results = provider.browse('spotify:top:tracks:aa')

    session_mock.get_toplist.assert_called_once_with(
        type=spotify.ToplistType.TRACKS, region='AA')
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


def test_browse_top_albums_countries_list(
        session_mock, sp_track_mock, provider):
    session_mock.get_toplist.return_value.tracks = [
        sp_track_mock, sp_track_mock]

    results = provider.browse('spotify:top:albums:countries')

    assert len(results) == 2
    assert models.Ref.directory(
        uri='spotify:top:albums:gb', name='United Kingdom') in results
    assert models.Ref.directory(
        uri='spotify:top:albums:us', name='United States') in results


def test_browse_personal_top_artists(session_mock, sp_artist_mock, provider):
    session_mock.get_toplist.return_value.artists = [
        sp_artist_mock, sp_artist_mock]

    results = provider.browse('spotify:top:artists:user')

    session_mock.get_toplist.assert_called_once_with(
        type=spotify.ToplistType.ARTISTS, region=spotify.ToplistRegion.USER)
    assert len(results) == 2
    assert results[0] == models.Ref.artist(
        uri='spotify:artist:abba', name='ABBA')
