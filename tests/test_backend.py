from __future__ import unicode_literals

import unittest

from mopidy_spotify.backend import SpotifyBackend


class BackendTest(unittest.TestCase):

    def setUp(self):
        config = {}
        self.backend = SpotifyBackend(config=config, audio=None)

    def test_uri_schemes(self):
        self.assertIn('spotify', self.backend.uri_schemes)
