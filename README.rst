**************
Mopidy-Spotify
**************

.. image:: https://pypip.in/v/Mopidy-Spotify/badge.png
    :target: https://crate.io/packages/Mopidy-Spotify/
    :alt: Latest PyPI version

.. image:: https://pypip.in/d/Mopidy-Spotify/badge.png
    :target: https://crate.io/packages/Mopidy-Spotify/
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
  Free or Spotify Unlimited, just Spotify Premium.

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


Project resources
=================

- `Source code <https://github.com/mopidy/mopidy-spotify>`_
- `Issue tracker <https://github.com/mopidy/mopidy-spotify/issues>`_
- `Download development snapshot <https://github.com/mopidy/mopidy-spotify/tarball/master#egg=Mopidy-Spotify-dev>`_


Changelog
=========

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
