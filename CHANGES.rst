Changelog
=========

v3.1.0 (2017-06-08)
-------------------

Feature release.

- Include the artists of each album in the search results. (PR: #118)

- Respect `spotify/timeout` setting when loading data from Spotify. (#129, PR:
  #139)

- Use OAuth to authenticate Spotify Web API requests, which has required
  authentication since 2017-05-29. The new config value `spotify/client_id` and
  `spotify/client_secret` must be set. Refer to the README for details. (#130,
  #142, PR: #143)

v3.0.0 (2016-02-15)
-------------------

Feature release.

- Require Mopidy 2.0.

- Minor adjustments to work with GStreamer 1.

v2.3.1 (2016-02-14)
-------------------

Bug fix release.

- Require Mopidy < 2 as Mopidy 2.0 breaks the audio API with the upgrade to
  GStreamer 1.

- Use the new Spotify Web API for search. Searching through libspotify has been
  discontinued and is not working anymore. (Fixes: #89)

- Note that search through the Spotify Web API doesn't return artists or date
  for albums. This also means that ``library.get_distinct()`` when given type
  ``albumartist`` or ``date`` and a query only returns an empty set.

- Emit a warning if config value ``spotify/search_album_count``,
  ``spotify/search_artist_count``, or ``spotify/search_track_count`` is greater
  than 50, and use 50 instead. 50 is the maximum value that the Spotify Web API
  allows. The maximum in the config schema is not changed to not break existing
  configs.

v2.3.0 (2016-02-06)
-------------------

Feature release.

- Ignore all audio data deliveries from libspotify when when a seek is in
  progress. This ensures that we don't deliver audio data from before the seek
  with timestamps from after the seek.

- Ignore duplicate end of track callbacks.

- Don't increase the audio buffer timestamp if the buffer is rejected by
  Mopidy. This caused audio buffers delivered after one or more rejected audio
  buffers to have too high timestamps.

- When changing tracks, block until Mopidy completes the appsrc URI change.
  Not blocking here might break gapless playback.

- Lookup of a playlist you're not subscribed to will now properly load all of
  the playlist's tracks. (Fixes: #81, PR: #82)

- Workaround teardown race outputing lots of short stack traces on Mopidy
  shutdown. (See #73 for details)

v2.2.0 (2015-11-15)
-------------------

Feature release.

- As Spotify now exposes your "Starred" playlist as a regular playlist, we no
  longer get your "Starred" playlist through the dedicated "Starred" API. This
  avoids your "Starred" playlist being returned twice. Lookup of
  ``spotify:user:<username>:starred`` URIs works as before. (Fixes: #71)

- Interpret album year "0" as unknown. (Fixes: #72)

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
