from __future__ import unicode_literals

import mock

from mopidy import models

import pytest

from mopidy_spotify import distinct, search


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


@pytest.yield_fixture
def search_mock(mopidy_album_mock, mopidy_artist_mock):
    patcher = mock.patch.object(distinct, 'search', spec=search)
    search_mock = patcher.start()
    search_mock.search.return_value = models.SearchResult(
        albums=[mopidy_album_mock], artists=[mopidy_artist_mock])
    yield search_mock
    patcher.stop()


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


@pytest.mark.parametrize('field,query,expected,types', [
    (
        'artist',
        {'album': ['Foo']},
        {'ABBA'},
        ['artist'],
    ),
    (
        'albumartist',
        {'album': ['Foo']},
        {'ABBA'},
        ['album'],
    ),
    (
        'album',
        {'artist': ['Bar']},
        {'DEF 456'},
        ['album'],
    ),
    (
        'date',
        {'artist': ['Bar']},
        {'2001'},
        ['album'],
    ),
])
def test_get_distinct_with_query(
        search_mock, provider, config, session_mock,
        field, query, expected, types):

    assert provider.get_distinct(field, query) == expected
    search_mock.search.assert_called_once_with(
        mock.ANY, mock.ANY, mock.ANY, query, types=types)
