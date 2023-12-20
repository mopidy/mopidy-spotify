import pytest
from mopidy import models

from mopidy_spotify import images


@pytest.fixture
def img_provider(provider):
    images._cache = {}
    return provider


def test_get_artist_images(web_client_mock, img_provider):
    uris = [
        "spotify:artist:4FCGgZrVQtcbDFEap3OAb2",
        "http://open.spotify.com/artist/0Nsz79ZcE8E4i3XZhCzZ1l",
    ]

    web_client_mock.get.return_value = {
        "artists": [
            {
                "id": "4FCGgZrVQtcbDFEap3OAb2",
                "images": [
                    {"height": 640, "url": "img://1/a", "width": 640},
                    {"height": 300, "url": "img://1/b", "width": 300},
                ],
            },
            {
                "id": "0Nsz79ZcE8E4i3XZhCzZ1l",
                "images": [{"height": 64, "url": "img://2/a", "width": 64}],
            },
        ]
    }

    result = img_provider.get_images(uris)

    web_client_mock.get.assert_called_once_with(
        "artists",
        params={"ids": "4FCGgZrVQtcbDFEap3OAb2,0Nsz79ZcE8E4i3XZhCzZ1l"},
    )

    assert len(result) == 2
    assert sorted(result.keys()) == sorted(uris)

    assert len(result[uris[0]]) == 2
    assert len(result[uris[1]]) == 1

    image1a = result[uris[0]][0]
    assert isinstance(image1a, models.Image)
    assert image1a.uri == "img://1/a"
    assert image1a.height == 640
    assert image1a.width == 640

    image1b = result[uris[0]][1]
    assert isinstance(image1b, models.Image)
    assert image1b.uri == "img://1/b"
    assert image1b.height == 300
    assert image1b.width == 300

    image2a = result[uris[1]][0]
    assert isinstance(image2a, models.Image)
    assert image2a.uri == "img://2/a"
    assert image2a.height == 64
    assert image2a.width == 64


def test_get_album_images(web_client_mock, img_provider):
    uris = ["http://play.spotify.com/album/1utFPuvgBHXzLJdqhCDOkg"]

    web_client_mock.get.return_value = {
        "albums": [
            {
                "id": "1utFPuvgBHXzLJdqhCDOkg",
                "images": [{"height": 640, "url": "img://1/a", "width": 640}],
            }
        ]
    }

    result = img_provider.get_images(uris)

    web_client_mock.get.assert_called_once_with(
        "albums", params={"ids": "1utFPuvgBHXzLJdqhCDOkg"}
    )

    assert len(result) == 1
    assert sorted(result.keys()) == sorted(uris)
    assert len(result[uris[0]]) == 1

    image = result[uris[0]][0]
    assert isinstance(image, models.Image)
    assert image.uri == "img://1/a"
    assert image.height == 640
    assert image.width == 640


def test_get_track_images(web_client_mock, img_provider):
    uris = ["spotify:track:41shEpOKyyadtG6lDclooa"]

    web_client_mock.get.return_value = {
        "tracks": [
            {
                "id": "41shEpOKyyadtG6lDclooa",
                "album": {
                    "uri": "spotify:album:1utFPuvgBHXzLJdqhCDOkg",
                    "images": [
                        {"height": 640, "url": "img://1/a", "width": 640}
                    ],
                },
            }
        ]
    }

    result = img_provider.get_images(uris)

    web_client_mock.get.assert_called_once_with(
        "tracks", params={"ids": "41shEpOKyyadtG6lDclooa"}
    )

    assert len(result) == 1
    assert sorted(result.keys()) == sorted(uris)
    assert len(result[uris[0]]) == 1

    image = result[uris[0]][0]
    assert isinstance(image, models.Image)
    assert image.uri == "img://1/a"
    assert image.height == 640
    assert image.width == 640


def test_get_track_images_bad_album_uri(web_client_mock, img_provider):
    uris = ["spotify:track:41shEpOKyyadtG6lDclooa"]

    web_client_mock.get.return_value = {
        "tracks": [
            {
                "id": "41shEpOKyyadtG6lDclooa",
                "album": {
                    "uri": "spotify:bad-data",
                    "images": [
                        {"height": 640, "url": "img://1/a", "width": 640}
                    ],
                },
            }
        ]
    }

    result = img_provider.get_images(uris)
    assert result == {}


def test_get_relinked_track_images(web_client_mock, img_provider):
    uris = ["spotify:track:4nqN0p0FjfH39G3hxeuKad"]

    web_client_mock.get.return_value = {
        "tracks": [
            {
                "id": "39S0DVDKeneEjsq4pV45PT",
                "linked_from": {
                    "id": "4nqN0p0FjfH39G3hxeuKad",
                    "type": "track",
                    "uri": "spotify:track:4nqN0p0FjfH39G3hxeuKad",
                },
                "album": {
                    "uri": "spotify:album:1utFPuvgBHXzLJdqhCDOkg",
                    "images": [
                        {"height": 640, "url": "img://1/a", "width": 640}
                    ],
                },
            }
        ]
    }

    result = img_provider.get_images(uris)

    web_client_mock.get.assert_called_once_with(
        "tracks", params={"ids": "4nqN0p0FjfH39G3hxeuKad"}
    )

    assert len(result) == 1
    assert sorted(result.keys()) == sorted(uris)
    assert len(result[uris[0]]) == 1

    image = result[uris[0]][0]
    assert isinstance(image, models.Image)
    assert image.uri == "img://1/a"
    assert image.height == 640
    assert image.width == 640


def test_get_playlist_image(web_client_mock, img_provider):
    uris = ["spotify:playlist:41shEpOKyyadtG6lDclooa", "foo:bar"]

    web_client_mock.get.return_value = {
        "id": "41shEpOKyyadtG6lDclooa",
        "images": [{"height": 640, "url": "img://1/a", "width": 640}],
    }

    result = img_provider.get_images(uris)

    web_client_mock.get.assert_called_once_with(
        "playlists/41shEpOKyyadtG6lDclooa"
    )

    assert len(result) == 1
    assert sorted(result.keys()) == ["spotify:playlist:41shEpOKyyadtG6lDclooa"]
    assert len(result[uris[0]]) == 1

    image = result[uris[0]][0]
    assert isinstance(image, models.Image)
    assert image.uri == "img://1/a"
    assert image.height == 640
    assert image.width == 640


def test_results_are_cached(web_client_mock, img_provider):
    uris = ["spotify:track:41shEpOKyyadtG6lDclooa"]

    web_client_mock.get.return_value = {
        "tracks": [
            {
                "id": "41shEpOKyyadtG6lDclooa",
                "album": {
                    "uri": "spotify:album:1utFPuvgBHXzLJdqhCDOkg",
                    "images": [
                        {"height": 640, "url": "img://1/a", "width": 640}
                    ],
                },
            }
        ]
    }

    result1 = img_provider.get_images(uris)
    result2 = img_provider.get_images(uris)

    assert web_client_mock.get.call_count == 1
    assert result1 == result2


def test_max_50_ids_per_request(web_client_mock, img_provider):
    uris = [f"spotify:track:{i}" for i in range(51)]

    web_client_mock.get.return_value = {}

    img_provider.get_images(uris)

    assert web_client_mock.get.call_count == 2

    request_ids_1 = web_client_mock.get.call_args_list[0][1]["params"]["ids"]
    assert request_ids_1 == ",".join(str(i) for i in range(50))

    request_ids_2 = web_client_mock.get.call_args_list[1][1]["params"]["ids"]
    assert request_ids_2 == "50"


def test_invalid_uri(img_provider, caplog):
    with caplog.at_level(5):
        result = img_provider.get_images(["foo:bar"])
    assert result == {}
    assert "Could not parse 'foo:bar' as a Spotify URI" in caplog.text


def test_no_uris_gives_no_results(img_provider):
    result = img_provider.get_images([])

    assert result == {}


def test_service_returns_empty_result(web_client_mock, img_provider):
    web_client_mock.get.return_value = {"tracks": [{}]}

    result = img_provider.get_images(["spotify:track:41shEpOKyyadtG6lDclooa"])

    assert result == {}


def test_service_returns_none_result(web_client_mock, img_provider):
    web_client_mock.get.return_value = {"tracks": None}

    result = img_provider.get_images(["spotify:track:41shEpOKyyadtG6lDclooa"])

    assert result == {}


def test_service_returns_none_result_playlist(web_client_mock, img_provider):
    web_client_mock.get.return_value = {"images": None}

    result = img_provider.get_images(
        ["spotify:playlist:41shEpOKyyadtG6lDclooa"]
    )

    assert result == {"spotify:playlist:41shEpOKyyadtG6lDclooa": ()}
