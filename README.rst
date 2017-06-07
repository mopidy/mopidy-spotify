**************
Mopidy-Spotify
**************

.. image:: https://img.shields.io/pypi/v/Mopidy-Spotify.svg?style=flat
    :target: https://pypi.python.org/pypi/Mopidy-Spotify/
    :alt: Latest PyPI version

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
  login with your Facebook account, and follow the instructions. However,
  sometimes that process can fail for users with Facebook logins, in which case
  you can create an app-specific password on Facebook by going to facebook.com >
  Settings > Security > App passwords > Generate app passwords, and generate one
  to use with Mopidy-Spotify.

- ``libspotify`` >= 12, < 13. The official C library from the `Spotify
  developer site <https://developer.spotify.com/technologies/libspotify/>`_.
  The package is available as ``libspotify12`` from
  `apt.mopidy.com <http://apt.mopidy.com/>`__.

- ``pyspotify`` >= 2.0.5. The ``libspotify`` Python wrapper. The package is
  available as ``python-spotify`` from apt.mopidy.com or ``pyspotify`` on PyPI.
  See https://pyspotify.mopidy.com/en/latest/installation/ for how to install
  it and its dependencies on most platforms.

- ``Mopidy`` >= 2.0. The music server that Mopidy-Spotify extends.

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
to your Mopidy configuration file and also visit 
https://www.mopidy.com/authenticate/#spotify to authorize this extension against
your Spotify account::

    [spotify]
    username = alice
    password = secret
    client_id = ... client_id value you got from mopidy.com ...
    client_secret = ... client_secret value you got from mopidy.com ...

The following configuration values are available:

- ``spotify/enabled``: If the Spotify extension should be enabled or not.
  Defaults to ``true``.

- ``spotify/username``: Your Spotify Premium username. You *must* provide this.

- ``spotify/password``: Your Spotify Premium password. You *must* provide this.

- ``spotify/client_id``: Your Spotify application client id. You *must* provide this.

- ``spotify/client_secret``: Your Spotify application secret key. You *must* provide this.

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
  results. Number between 0 and 50. Defaults to 20.

- ``spotify/search_artist_count``: Maximum number of artists returned in search
  results. Number between 0 and 50. Defaults to 10.

- ``spotify/search_track_count``: Maximum number of tracks returned in search
  results. Number between 0 and 50. Defaults to 50.

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


Credits
=======

- Original author: `Stein Magnus Jodal <https://github.com/jodal>`__
- Current maintainer: `Stein Magnus Jodal <https://github.com/jodal>`__
- `Contributors <https://github.com/mopidy/mopidy-spotify/graphs/contributors>`_
