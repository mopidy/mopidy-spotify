**************
Mopidy-Spotify
**************

.. image:: https://img.shields.io/pypi/v/Mopidy-Spotify
    :target: https://pypi.org/project/Mopidy-Spotify/
    :alt: Latest PyPI version

.. image:: https://img.shields.io/github/actions/workflow/status/mopidy/mopidy-spotify/ci.yml?branch=main
    :target: https://github.com/mopidy/mopidy-spotify/actions
    :alt: CI build status

.. image:: https://img.shields.io/codecov/c/gh/mopidy/mopidy-spotify
    :target: https://codecov.io/gh/mopidy/mopidy-spotify
    :alt: Test coverage

`Mopidy <https://mopidy.com/>`_ extension for playing music from
`Spotify <https://www.spotify.com/>`_.


Status  :warning:
=================

Spotify have recently disabled username and password login for playback
(`#394 <https://github.com/mopidy/mopidy-spotify/issues/394>`_) and we
now utilise access-token login. You no longer need to provide your
Spotify account username or password.

Mopidy-Spotify currently has no support for the following:

- Seeking

- Gapless playback

- Volume normalization

- Saving items to My Music (`#108 <https://github.com/mopidy/mopidy-spotify/issues/108>`_) -
  possible via web API

- Podcasts (`#201 <https://github.com/mopidy/mopidy-spotify/issues/201>`_) -
  now possible

- Radio (`#9 <https://github.com/mopidy/mopidy-spotify/issues/9>`_) - unavailable?

- Spotify Connect (`#14 <https://github.com/mopidy/mopidy-spotify/issues/14>`_)

Working support for the following features is currently available:

- Playback

- Search

- Playlists (read-only)

- Top lists and Your Music (read-only)

- Lookup by URI


Dependencies
============

- A Spotify Premium subscription. Mopidy-Spotify **will not** work with Spotify
  Free, just Spotify Premium.

- ``Mopidy`` >= 3.4. The music server that Mopidy-Spotify extends.

- ``gst-plugins-spotify``, the `GStreamer Rust Plugin
  <https://gitlab.freedesktop.org/gstreamer/gst-plugins-rs>`_ for Spotify
  playback, based on `librespot <https://github.com/librespot-org/librespot/>`_.
  *This plugin is not yet available from apt.mopidy.com*. It must be either
  `built from source
  <https://github.com/kingosticks/gst-plugins-rs-build/tree/main?tab=readme-ov-file#native-compile>`_
  or `Debian packages are available
  <https://github.com/kingosticks/gst-plugins-rs-build/releases/latest>`_
  for some platforms. 
  
  **We currently require a forked version of this plugin which supports
  token-based login.** This can be found `here <https://gitlab.freedesktop.org/kingosticks/gst-plugins-rs/-/tree/spotify-access-token-logging>`_.

Verify the GStreamer spotify plugin is correctly installed:: 

    gst-inspect-1.0 spotify


Installation
============

Install by running::

    sudo python3 -m pip install --break-system-packages Mopidy-Spotify==5.0.0a3


Configuration
=============

Before starting Mopidy, you must add your Spotify Premium username and password
to your Mopidy configuration file and also visit
https://mopidy.com/ext/spotify/#authentication
to authorize this extension against your Spotify account::

    [spotify]
    client_id = ... client_id value you got from mopidy.com ...
    client_secret = ... client_secret value you got from mopidy.com ...

The following configuration values are available:

- ``spotify/enabled``: If the Spotify extension should be enabled or not.
  Defaults to ``true``.

- ``spotify/username``: Your Spotify Premium username. Obsolete.

- ``spotify/password``: Your Spotify Premium password. Obsolete.

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

- ``spotify/cache_size``: Maximum cache size in MiB. Set to ``0`` for unlimited. Defaults to ``8192``.

- ``spotify/allow_playlists``: Whether or not playlists should be exposed.
  Defaults to ``true``.

- ``spotify/search_album_count``: Maximum number of albums returned in search
  results. Number between 0 and 50. Defaults to 20.

- ``spotify/search_artist_count``: Maximum number of artists returned in search
  results. Number between 0 and 50. Defaults to 10.

- ``spotify/search_track_count``: Maximum number of tracks returned in search
  results. Number between 0 and 50. Defaults to 50.


Project resources
=================

- `Source code <https://github.com/mopidy/mopidy-spotify>`_
- `Issue tracker <https://github.com/mopidy/mopidy-spotify/issues>`_
- `Changelog <https://github.com/mopidy/mopidy-spotify/releases>`_


Credits
=======

- Original author: `Stein Magnus Jodal <https://github.com/jodal>`__
- Current maintainer: `Nick Steel <https://github.com/kingosticks>`__
- `Contributors <https://github.com/mopidy/mopidy-spotify/graphs/contributors>`_
