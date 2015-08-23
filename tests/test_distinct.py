from __future__ import unicode_literals

import pytest

import spotify


@pytest.fixture
def session_mock_with_playlists(
        session_mock, sp_playlist_mock, sp_unloaded_playlist_mock,
        sp_playlist_folder_start_mock, sp_playlist_folder_end_mock):

    session_mock.playlist_container = [
        sp_playlist_folder_start_mock,
        sp_playlist_mock,
        sp_unloaded_playlist_mock,
        sp_playlist_folder_end_mock,
    ]
    return session_mock


@pytest.fixture
def session_mock_with_search(
        session_mock,
        sp_album_mock, sp_unloaded_album_mock,
        sp_artist_mock, sp_unloaded_artist_mock):

    session_mock.connection.state = spotify.ConnectionState.LOGGED_IN
    session_mock.search.return_value.albums = [
        sp_album_mock, sp_unloaded_album_mock]
    session_mock.search.return_value.artists = [
        sp_artist_mock, sp_unloaded_artist_mock]
    return session_mock


@pytest.mark.parametrize('field', [
    'composer',
    'performer',
    'genre',
    'unknown-field-type',
])
def test_get_distinct_unsupported_field_types_returns_nothing(provider, field):
    assert provider.get_distinct(field) == set()


@pytest.mark.parametrize('field,expected', [
    ('artist', {'ABBA'}),
    ('albumartist', {'ABBA'}),
    ('album', {'DEF 456'}),
    ('date', {'2001'}),
])
def test_get_distinct_without_query_when_playlists_enabled(
        session_mock_with_playlists, provider, field, expected):

    assert provider.get_distinct(field) == expected


@pytest.mark.parametrize('field', [
    'artist',
    'albumartist',
    'album',
    'date',
])
def test_get_distinct_without_query_returns_nothing_when_playlists_disabled(
        provider, config, field):

    config['spotify']['allow_playlists'] = False

    assert provider.get_distinct(field) == set()


@pytest.mark.parametrize('field,query,expected,search_args,search_kwargs', [
    (
        'artist',
        {'album': ['Foo']},
        {'ABBA'},
        ('album:"Foo"',),
        dict(album_count=0, artist_count=10, track_count=0),
    ),
    (
        'albumartist',
        {'album': ['Foo']},
        {'ABBA'},
        ('album:"Foo"',),
        dict(album_count=20, artist_count=0, track_count=0),
    ),
    (
        'album',
        {'artist': ['Bar']},
        {'DEF 456'},
        ('artist:"Bar"',),
        dict(album_count=20, artist_count=0, track_count=0),
    ),
    (
        'date',
        {'artist': ['Bar']},
        {'2001'},
        ('artist:"Bar"',),
        dict(album_count=20, artist_count=0, track_count=0),
    ),
])
def test_get_distinct_with_query(
        session_mock_with_search, provider,
        field, query, expected, search_args, search_kwargs):

    assert provider.get_distinct(field, query) == expected
    session_mock_with_search.search.assert_called_once_with(
        *search_args, **search_kwargs)


def test_get_distinct_with_query_when_offline(
        session_mock_with_search, provider):

    session_mock_with_search.connection.state = spotify.ConnectionState.OFFLINE

    assert provider.get_distinct('artist', {'album': ['Foo']}) == set()
    assert session_mock_with_search.search.return_value.load.call_count == 0
