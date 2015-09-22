**************
Mopidy-Spotify
**************

.. image:: https://img.shields.io/pypi/v/Mopidy-Spotify.svg?style=flat
    :target: https://pypi.python.org/pypi/Mopidy-Spotify/
    :alt: Latest PyPI version

.. image:: https://img.shields.io/pypi/dm/Mopidy-Spotify.svg?style=flat
    :target: https://pypi.python.org/pypi/Mopidy-Spotify/
    :alt: Number of PyPI downloads

.. image:: https://img.shields.io/travis/mopidy/mopidy-spotify/develop.svg?style=flat
    :target: https://travis-ci.org/mopidy/mopidy-spotify
    :alt: Travis CI build status

.. image:: https://img.shields.io/coveralls/mopidy/mopidy-spotify/develop.svg?style=flat
   :target: https://coveralls.io/r/mopidy/mopidy-spotify
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

- ``pyspotify`` >= 2.0. The ``libspotify`` python wrapper. The package is
  available as ``python-spotify`` from apt.mopidy.com or ``pyspotify`` on PyPI.

- ``Mopidy`` >= 1.1. The music server that Mopidy-Spotify extends.

If you install Mopidy-Spotify from apt.mopidy.com, AUR, or Homebrew, these
dependencies are installed automatically.


Installation
============

Debian/Ubuntu/Raspbian: Install the ``mopidy-spotify`` package from
`apt.mopidy.com <http://apt.mopidy.com/>`_::

    sudo apt-get install mopidy-spotify

Arch Linux: Install the ``mopidy-spotify`` package from
`AUR <https://aur.archlinux.org/packages/mopidy-spotify/>`_::

    yaourt -S mopidy-spotify

OS X: Install the ``mopidy-spotify`` package from the
`mopidy/mopidy <https://github.com/mopidy/homebrew-mopidy>`_ Homebrew tap::

    brew install mopidy-spotify

Else: Install the dependencies listed above yourself, and then install the
package from PyPI::

    pip install Mopidy-Spotify


Configuration
=============

Before starting Mopidy, you must add your Spotify Premium username and password
to your Mopidy configuration file::

    [spotify]
    username = alice
    password = secret

The following configuration values are available:

- ``spotify/enabled``: If the Spotify extension should be enabled or not.
  Defaults to ``true``.

- ``spotify/username``: Your Spotify Premium username. You *must* provide this.

- ``spotify/password``: Your Spotify Premium password. You *must* provide this.

- ``spotify/bitrate``: Audio bitrate in kbps. ``96``, ``160``, or ``320``.
  Defaults to ``160``.

- ``spotify/volume_normalization``: Whether volume normalization is active or
  not. Defaults to ``true``.

- ``spotify/timeout``: Seconds before giving up waiting for search results,
  etc. Defaults to ``10``.

- ``spotify/allow_cache``: Whether to allow caching. The cache is stored in a
  "spotify" directory within Mopidy's ``core/cache_dir``. Defaults to ``true``.

- ``spotify/allow_network``: Whether to allow network access or not. Defaults
  to ``true``.

- ``spotify/allow_playlists``: Whether or not playlists should be exposed.
  Defaults to ``true``.

- ``spotify/search_album_count``: Maximum number of albums returned in search
  results. Number between 0 and 200. Defaults to 20.

- ``spotify/search_artist_count``: Maximum number of artists returned in search
  results. Number between 0 and 200. Defaults to 10.

- ``spotify/search_track_count``: Maximum number of tracks returned in search
  results. Number between 0 and 200. Defaults to 50.

- ``spotify/toplist_countries``: Comma separated list of two letter ISO country
  codes to get toplists for. Defaults to blank, which is interpreted as all
  countries that Spotify is available in.

- ``spotify/private_session``: Whether to use a private Spotify session. Turn
  on private session to disable sharing of played tracks with friends through
  the Spotify activity feed, Last.fm scrobbling, and Facebook. This only
  affects social sharing done by Spotify, not by other Mopidy extensions.
  Defaults to ``false``.


Project resources
=================

- `Source code <https://github.com/mopidy/mopidy-spotify>`_
- `Issue tracker <https://github.com/mopidy/mopidy-spotify/issues>`_
- `Download development snapshot <https://github.com/mopidy/mopidy-spotify/tarball/develop#egg=Mopidy-Spotify-dev>`_


Changelog
=========

v2.1.0 (2015-09-22)
-------------------

Feature release.

- Require Requests >= 2.0.

- Support using a proxy when connecting to Spotify. This was forgotten in the
  2.0 reimplementation. (Fixes: #68)

- Support using a proxy when accessing Spotify's web API to get cover and
  artist imagery.

v2.0.1 (2015-08-23)
-------------------

Bug fix release.

- Filter out ``None`` from ``library.get_distinct()`` return values. (Fixes:
  #63)

v2.0.0 (2015-08-11)
-------------------

Rewrite using pyspotify 2. Should have feature parity with Mopidy-Spotify 1.

**Config**

- Add ``spotify/volume_normalization`` config. (Fixes: #13)

- Add ``spotify/allow_network`` config which can be used to force
  Mopidy-Spotify to stay offline. This is mostly useful for testing during
  development.

- Add ``spotify/allow_playlists`` config which can be used to disable all
  access to playlists on the Spotify account. Useful where Mopidy is shared by
  multiple users. (Fixes: #25)

- Make maximum number of returned results configurable through
  ``spotify/search_album_count``, ``spotify/search_artist_count``, and
  ``spotify/search_track_count``.

- Add ``spotify/private_session`` config.

- Change ``spotify/toplist_countries`` default value to blank, which is now
  interpreted as all supported countries instead of no countries.

- Removed ``spotify/cache_dir`` and ``spotify/settings_dir`` config values. We
  now use a "spotify" directory in the ``core/cache_dir`` and
  ``core/data_dir`` directories defined in Mopidy's configuration.

- Add ``spotify/allow_cache`` config value to make it possible to disable
  caching.

**Browse**

- Add browsing of top albums and top artists, in additon to top tracks.

- Add browsing by current user's country, in addition to personal, global and
  per-country browsing.

- Add browsing of artists, which includes the artist's top tracks and albums.

- Update list of countries Spotify is available in and provides toplists for.

**Lookup**

- Adding an artist by URI will now first find all albums by the artist and
  then all tracks in the albums. This way, the returned tracks are grouped by
  album and they are sorted by track number. (Fixes: #7)

- When adding an artist by URI, all albums that are marked as "compilations"
  or where the album artist is "Various Artists" are now ignored. (Fixes: #5)

**Library**

- The library provider method ``get_distinct()`` is now supported. When called
  without a query, the tracks in the user's playlists is used as the data
  source. When called with a query, a Spotify search is used as the data
  source. This addition makes the library view in some notable MPD clients,
  like ncmpcpp, become quite fast and usable with Spotify. (Fixes: #50)

**Playback**

- If another Spotify client starts playback with the same account, we get a
  "play token lost" event. Previously, Mopidy-Spotify would unconditionally
  pause Mopidy playback if this happened. Now, we only pause playback if we're
  currently playing music from Spotify. (Fixes: #1)

v1.4.0 (2015-05-19)
-------------------

- Update to not use deprecated Mopidy audio APIs.

- Use strings and not ints for the model's date field. This is required for
  compatibility with the model validation added in Mopidy 1.1. (Fixes: #52)

- Fix error causing the image of every 50th URI in a ``library.get_images()``
  call to not be looked up and returned.

- Fix handling of empty search queries. This was still using the removed
  ``playlists.playlists`` to fetch all your tracks.

- Update the ``SpotifyTrack`` proxy model to work with Mopidy 1.1 model
  changes.

- Updated to work with the renaming of ``mopidy.utils`` to ``mopidy.internal``
  in Mopidy 1.1.

v1.3.0 (2015-03-25)
-------------------

- Require Mopidy >= 1.0.

- Update to work with new playback API in Mopidy 1.0.

- Update to work with new playlists API in Mopidy 1.0.

- Update to work with new search API in Mopidy 1.0.

- Add ``library.get_images()`` support for cover art.

v1.2.0 (2014-07-21)
-------------------

- Add support for browsing playlists and albums. Needed to allow music
  discovery extensions expose these in a clean way.

- Fix loss of audio when resuming from paused, when caused by another Spotify
  client starting playback. (Fixes: #2, PR: #19)

v1.1.3 (2014-02-18)
-------------------

- Switch to new backend API locations, required by the upcoming Mopidy 0.19
  release.

v1.1.2 (2014-02-18)
-------------------

- Wait for track to be loaded before playing it. This fixes playback of tracks
  looked up directly by URI, and not through a playlist or search. (Fixes:
  mopidy/mopidy#675)

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
