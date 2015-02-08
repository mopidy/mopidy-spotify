from __future__ import unicode_literals

import contextlib
import logging
import time


logger = logging.getLogger(__name__)


@contextlib.contextmanager
def time_logger(name):
    start = time.time()
    yield
    logger.debug('%s took %dms', name, (time.time() - start) * 1000)
