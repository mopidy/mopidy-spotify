from __future__ import unicode_literals

import logging

from mopidy import backend


logger = logging.getLogger(__name__)


class SpotifyPlaybackProvider(backend.PlaybackProvider):

    def __init__(self, *args, **kwargs):
        super(SpotifyPlaybackProvider, self).__init__(*args, **kwargs)
