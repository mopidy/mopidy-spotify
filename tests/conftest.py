from __future__ import unicode_literals

import mock

import pytest

import spotify

from mopidy_spotify import backend


@pytest.yield_fixture
def spotify_mock():
    patcher = mock.patch.object(backend, 'spotify', spec=spotify)
    yield patcher.start()
    patcher.stop()
