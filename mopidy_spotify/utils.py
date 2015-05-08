from __future__ import unicode_literals

import contextlib
import locale
import logging
import time


logger = logging.getLogger(__name__)
TRACE = logging.getLevelName('TRACE')


def locale_decode(bytestr):
    try:
        return unicode(bytestr)
    except UnicodeError:
        return bytes(bytestr).decode(locale.getpreferredencoding())


@contextlib.contextmanager
def time_logger(name, level=TRACE):
    start = time.time()
    yield
    logger.log(level, '%s took %dms', name, (time.time() - start) * 1000)
