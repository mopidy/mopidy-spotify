from __future__ import unicode_literals

import json
import urllib2
from StringIO import StringIO

import mock

from mopidy import models

import pytest

from mopidy_spotify import images


@pytest.yield_fixture
def urllib_mock():
    patcher = mock.patch.object(images, 'urllib2', spec=urllib2)
    yield patcher.start()
    patcher.stop()


@pytest.fixture
def img_provider(provider):
    images._cache = {}
    return provider


def test_get_artist_images(img_provider, urllib_mock):
    uris = [
        'spotify:artist:4FCGgZrVQtcbDFEap3OAb2',
        'http://open.spotify.com/artist/0Nsz79ZcE8E4i3XZhCzZ1l',
    ]

    urllib_mock.urlopen.return_value = StringIO(json.dumps({
        'artists': [
            {
                'id': '4FCGgZrVQtcbDFEap3OAb2',
                'images': [
                    {
                        'height': 640,
                        'url': 'img://1/a',
                        'width': 640,
                    },
                    {
                        'height': 300,
                        'url': 'img://1/b',
                        'width': 300,
                    },
                ]
            },
            {
                'id': '0Nsz79ZcE8E4i3XZhCzZ1l',
                'images': [
                    {
                        'height': 64,
                        'url': 'img://2/a',
                        'width': 64
                    }
                ]
            }
        ]
    }))

    result = img_provider.get_images(uris)

    urllib_mock.urlopen.assert_called_once_with(
        'https://api.spotify.com/v1/artists/?ids='
        '0Nsz79ZcE8E4i3XZhCzZ1l,4FCGgZrVQtcbDFEap3OAb2')
    assert len(result) == 2
    assert sorted(result.keys()) == sorted(uris)

    assert len(result[uris[0]]) == 2
    assert len(result[uris[1]]) == 1

    image1a = result[uris[0]][0]
    assert isinstance(image1a, models.Image)
    assert image1a.uri == 'img://1/a'
    assert image1a.height == 640
    assert image1a.width == 640

    image1b = result[uris[0]][1]
    assert isinstance(image1b, models.Image)
    assert image1b.uri == 'img://1/b'
    assert image1b.height == 300
    assert image1b.width == 300

    image2a = result[uris[1]][0]
    assert isinstance(image2a, models.Image)
    assert image2a.uri == 'img://2/a'
    assert image2a.height == 64
    assert image2a.width == 64


def test_get_album_images(img_provider, urllib_mock):
    uris = [
        'http://play.spotify.com/album/1utFPuvgBHXzLJdqhCDOkg',
    ]

    urllib_mock.urlopen.return_value = StringIO(json.dumps({
        'albums': [
            {
                'id': '1utFPuvgBHXzLJdqhCDOkg',
                'images': [
                    {
                        'height': 640,
                        'url': 'img://1/a',
                        'width': 640,
                    }
                ]
            }
        ]
    }))

    result = img_provider.get_images(uris)

    urllib_mock.urlopen.assert_called_once_with(
        'https://api.spotify.com/v1/albums/?ids=1utFPuvgBHXzLJdqhCDOkg')
    assert len(result) == 1
    assert sorted(result.keys()) == sorted(uris)
    assert len(result[uris[0]]) == 1

    image = result[uris[0]][0]
    assert isinstance(image, models.Image)
    assert image.uri == 'img://1/a'
    assert image.height == 640
    assert image.width == 640


def test_get_track_images(img_provider, urllib_mock):
    uris = [
        'spotify:track:41shEpOKyyadtG6lDclooa',
    ]

    urllib_mock.urlopen.return_value = StringIO(json.dumps({
        'tracks': [
            {
                'id': '41shEpOKyyadtG6lDclooa',
                'album': {
                    'uri': 'spotify:album:1utFPuvgBHXzLJdqhCDOkg',
                    'images': [
                        {
                            'height': 640,
                            'url': 'img://1/a',
                            'width': 640,
                        }
                    ]
                }
            }
        ]
    }))

    result = img_provider.get_images(uris)

    urllib_mock.urlopen.assert_called_once_with(
        'https://api.spotify.com/v1/tracks/?ids=41shEpOKyyadtG6lDclooa')
    assert len(result) == 1
    assert sorted(result.keys()) == sorted(uris)
    assert len(result[uris[0]]) == 1

    image = result[uris[0]][0]
    assert isinstance(image, models.Image)
    assert image.uri == 'img://1/a'
    assert image.height == 640
    assert image.width == 640


def test_results_are_cached(img_provider, urllib_mock):
    uris = [
        'spotify:track:41shEpOKyyadtG6lDclooa',
    ]

    urllib_mock.urlopen.return_value = StringIO(json.dumps({
        'tracks': [
            {
                'id': '41shEpOKyyadtG6lDclooa',
                'album': {
                    'uri': 'spotify:album:1utFPuvgBHXzLJdqhCDOkg',
                    'images': [
                        {
                            'height': 640,
                            'url': 'img://1/a',
                            'width': 640,
                        }
                    ]
                }
            }
        ]
    }))

    result1 = img_provider.get_images(uris)
    result2 = img_provider.get_images(uris)

    assert urllib_mock.urlopen.call_count == 1
    assert result1 == result2


def test_max_50_ids_per_request(img_provider, urllib_mock):
    uris = ['spotify:track:%d' for i in range(51)]

    urllib_mock.urlopen.return_value = StringIO('{}')

    img_provider.get_images(uris)

    assert urllib_mock.urlopen.call_count == 2

    request_url_1 = urllib_mock.urlopen.mock_calls[0]
    assert request_url_1.endswith(','.join(str(i) for i in range(50)))

    request_url_2 = urllib_mock.urlopen.mock_calls[1]
    assert request_url_2.endswith('ids=50')


def test_invalid_uri_fails(img_provider):
    with pytest.raises(ValueError) as exc:
        img_provider.get_images(['foo:bar'])

    assert str(exc.value) == "Could not parse u'foo:bar' as a Spotify URI"


def test_no_uris_gives_no_results(img_provider):
    result = img_provider.get_images([])

    assert result == {}


def test_service_returns_invalid_json(img_provider, urllib_mock, caplog):
    urllib_mock.urlopen.return_value = StringIO('[}')

    result = img_provider.get_images(['spotify:track:41shEpOKyyadtG6lDclooa'])

    assert result == {}
    assert "failed: No JSON object could be decoded" in caplog.text()


def test_service_returns_empty_result(img_provider, urllib_mock):
    urllib_mock.urlopen.return_value = StringIO(json.dumps({'tracks': [{}]}))

    result = img_provider.get_images(['spotify:track:41shEpOKyyadtG6lDclooa'])

    assert result == {}
