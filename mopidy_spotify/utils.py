from __future__ import unicode_literals

import logging
import time

logger = logging.getLogger(__name__)


def wait_for_object_to_load(spotify_obj, timeout):
    # XXX Sleeping to wait for the Spotify object to load is an ugly hack,
    # but it works. We should look into other solutions for this.
    wait_until = time.time() + timeout
    while not spotify_obj.is_loaded():
        time.sleep(0.1)
        if time.time() > wait_until:
            logger.debug(
                'Timeout: Spotify object did not load in %ds', timeout)
            return
