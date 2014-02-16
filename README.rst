**************
Mopidy-Spotify
**************

.. image:: https://pypip.in/v/Mopidy-Spotify/badge.png
    :target: https://pypi.python.org/pypi/Mopidy-Spotify/
    :alt: Latest PyPI version

.. image:: https://pypip.in/d/Mopidy-Spotify/badge.png
    :target: https://pypi.python.org/pypi/Mopidy-Spotify/
    :alt: Number of PyPI downloads

.. image:: https://travis-ci.org/mopidy/mopidy-spotify.png?branch=master
    :target: https://travis-ci.org/mopidy/mopidy-spotify
    :alt: Travis CI build status

.. image:: https://coveralls.io/repos/mopidy/mopidy-spotify/badge.png?branch=master
   :target: https://coveralls.io/r/mopidy/mopidy-spotify?branch=master
   :alt: Test coverage

`Mopidy <http://www.mopidy.com/>`_ extension for playing music from
`Spotify <http://www.spotify.com/>`_.


Dependencies
============

- A Spotify Premium subscription. Mopidy-Spotify **will not** work with Spotify
  Free, just Spotify Premium.

- A non-Facebook Spotify username and password. If you created your account
  through Facebook you'll need to create a "device password" to be able to use
  Mopidy-Spotify. Go to http://www.spotify.com/account/set-device-password/,
  login with your Facebook account, and follow the instructions.

- ``libspotify`` >= 12, < 13. The official C library from the `Spotify
  developer site <https://developer.spotify.com/technologies/libspotify/>`_.
  The package is available as ``libspotify12`` from
  `apt.mopidy.com <http://apt.mopidy.com/>`__.

- ``pyspotify`` >= 1.9, < 2. The ``libspotify`` python wrapper. The package is
  available as ``python-spotify`` from apt.mopidy.com or ``pyspotify`` on PyPI.

- ``Mopidy`` >= 0.16. The music server that Mopidy-Spotify extends.

If you install Mopidy-Spotify from apt.mopidy.com, these dependencies are
installed automatically.


Installation
============

Install by running::

    pip install Mopidy-Spotify

Or, if available, install the Debian/Ubuntu package from `apt.mopidy.com
<http://apt.mopidy.com/>`_.


Configuration
=============

Before starting Mopidy, you must add your Spotify Premium username and password
to your Mopidy configuration file::

    [spotify]
    username = alice
    password = secret

The following configuration values are available:

- ``spotify/enabled``: If the Spotify extension should be enabled or not.
- ``spotify/username``: Your Spotify Premium username.
- ``spotify/password``: Your Spotify Premium password.
- ``spotify/bitrate``: Audio bitrate in kbps. 96, 160 or 320. Defaults to 160.
- ``spotify/timeout``: Seconds before giving up waiting for search results,
  etc. Defaults to 10 seconds.
- ``spotify/cache_dir``: The dir where the Spotify extension caches data.
  Defaults to ``$XDG_CACHE_DIR/mopidy/spotify``, which usually means
  ``~/.cache/mopidy/spotify``. If set to an empty string, caching is disabled.
- ``spotify/settings_dir``: The dir where the Spotify extension stores
  libspotify settings. Defaults to ``$XDG_CONFIG_DIR/mopidy/spotify``, which
  usually means ``~/.config/mopidy/spotify``.
- ``spotify/toplist_countries``: Comma separated list of two letter country
  domains to get toplists for.


Project resources
=================

- `Source code <https://github.com/mopidy/mopidy-spotify>`_
- `Issue tracker <https://github.com/mopidy/mopidy-spotify/issues>`_
- `Download development snapshot <https://github.com/mopidy/mopidy-spotify/tarball/master#egg=Mopidy-Spotify-dev>`_


Changelog
=========

v1.1.1 (2014-02-16)
-------------------

- Change requirement on pyspotify from ``>= 1.9, < 2`` to ``>= 1.9, < 1.999``,
  so that it is parsed correctly and pyspotify 1.x is installed instead of 2.x.

v1.1.0 (2014-01-20)
-------------------

- Require Mopidy >= 0.18.

- Change ``library.lookup()`` to return tracks even if they are unplayable.
  There's no harm in letting them be added to the tracklist, as Mopidy will
  simply skip to the next track when failing to play the track. (Fixes:
  mopidy/mopidy#606)

- Added basic library browsing support that exposes user, global and country
  toplists.

v1.0.3 (2013-12-15)
-------------------

- Change search field ``track`` to ``track_name`` for compatibility with
  Mopidy 0.17. (Fixes: mopidy/mopidy#610)

v1.0.2 (2013-11-19)
-------------------

- Add ``spotify/settings_dir`` config value so that libspotify settings can be
  stored to another location than the libspotify cache. This also allows
  ``spotify/cache_dir`` to be unset, since settings are now using it's own
  config value.

- Make the ``spotify/cache_dir`` config value optional, so that it can be set
  to an empty string to disable caching.

v1.0.1 (2013-10-28)
-------------------

- Support searches from Mopidy that are using the ``albumartist`` field type,
  added in Mopidy 0.16.

- Ignore the ``track_no`` field in search queries, added in Mopidy 0.16.

- Abort Spotify searches immediately if the search query is empty instead of
  waiting for the 10s timeout before returning an empty search result.

v1.0.0 (2013-10-08)
-------------------

- Moved extension out of the main Mopidy project.
