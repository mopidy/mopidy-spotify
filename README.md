# mopidy-spotify

[![Latest PyPI version](https://img.shields.io/pypi/v/mopidy-spotify)](https://pypi.org/p/mopidy-spotify)
[![CI build status](https://img.shields.io/github/actions/workflow/status/mopidy/mopidy-spotify/ci.yml)](https://github.com/mopidy/mopidy-spotify/actions/workflows/ci.yml)
[![Test coverage](https://img.shields.io/codecov/c/gh/mopidy/mopidy-spotify)](https://codecov.io/gh/mopidy/mopidy-spotify)

[Mopidy](https://mopidy.com/) extension for playing music from [Spotify](https://www.spotify.com/).

## Status

> [!WARNING]
> Spotify no longer accepts third-party Web API access tokens for librespot
> playback. Use `mopidy spotify auth playback` to create the separate desktop-client
> credentials required for playback. Details at
> [#437](https://github.com/mopidy/mopidy-spotify/issues/437).

> [!WARNING]
> Spotify has introduced refresh token expiration as described in this
> [blogpost](https://developer.spotify.com/blog/2026-06-18-refresh-token-expiration).
> In practice this means you'll have to re-authenticate every six months going forward.

> [!WARNING]
> Spotify have recently disabled username and password login for playback
> ([#394](https://github.com/mopidy/mopidy-spotify/issues/394)). The playback
> authorization command replaces username and password login.

Mopidy-Spotify currently has no support for the following:

- Seeking
- Gapless playback
- Volume normalization
- Saving items to My Music ([#108](https://github.com/mopidy/mopidy-spotify/issues/108)) -
  possible via web API
- Podcasts ([#201](https://github.com/mopidy/mopidy-spotify/issues/201)) -
  now possible
- Radio ([#9](https://github.com/mopidy/mopidy-spotify/issues/9)) - unavailable?
- Spotify Connect ([#14](https://github.com/mopidy/mopidy-spotify/issues/14))

Working support for the following features is currently available:

- Playback
- Search
- Playlists (read-only)
- Top lists and Your Music (read-only)
- Lookup by URI

## Dependencies

- A Spotify Premium subscription. Mopidy-Spotify **will not** work with Spotify
  Free, just Spotify Premium.

- Mopidy >= 3.4. The music server that Mopidy-Spotify extends.

- `gst-plugins-spotify`, the
  [GStreamer Rust Plugin](https://gitlab.freedesktop.org/gstreamer/gst-plugins-rs) for Spotify
  playback, based on [librespot](https://github.com/librespot-org/librespot/).
  _This plugin is not yet available from apt.mopidy.com_. It must be either
  [built from source](https://github.com/kingosticks/gst-plugins-rs-build/tree/main?tab=readme-ov-file#native-compile)
  or
  [Debian packages are available](https://github.com/kingosticks/gst-plugins-rs-build/releases/latest)
  for some platforms.

**We currently prefer a forked version of this plugin which provides better logging.**
Details in release notes [here](https://github.com/kingosticks/gst-plugins-rs-build/releases/latest).

Verify the GStreamer spotify plugin is correctly installed:

```sh
gst-inspect-1.0 spotifyaudiosrc | grep Version | awk '{print $2}'
```

## Installation

Install by running:

```sh
sudo python3 -m pip install --break-system-packages mopidy-spotify
```

## Configuration

Mopidy-Spotify uses separate authorization for Spotify's public Web API and for
librespot playback. Authorize both before starting Mopidy:

```sh
mopidy spotify auth web
mopidy spotify auth playback
```

`auth web` displays a URL for the public Web API PKCE flow. Open it, approve
access in Spotify, then paste the result shown by the browser into the terminal.
The command stores the refresh token locally; the website never receives it.

`auth playback` runs the `gstspotify-auth` helper installed with recent
`gst-plugin-spotify` packages. It uses Spotify's desktop-client authorization
and stores reusable librespot credentials in `credentials-cache`.

These credentials are intentionally not shared. Public Web API tokens fail
librespot playback with `INVALID_CREDENTIALS`, while desktop-client playback
credentials cannot be used with Spotify's public Web API.

Inline storage is the default. To keep the refresh token in the operating
system keyring, install the optional dependency and select keyring storage:

```sh
python3 -m pip install 'mopidy-spotify[keyring]'
mopidy spotify auth web --storage keyring
```

The selected backend is recorded in `auth.json`. Mopidy-Spotify does not fall
back to inline storage if a selected keyring entry or backend is unavailable.

Run both commands as the same operating-system user that runs Mopidy and with
the same configuration. For a typical system service installation, use:

```sh
sudo -u mopidy mopidy --config /etc/mopidy/mopidy.conf spotify auth web
sudo -u mopidy mopidy --config /etc/mopidy/mopidy.conf spotify auth playback
```

The Web command writes `auth.json` below Mopidy's Spotify data directory,
normally `core/data_dir/spotify/auth.json`. The playback command writes
`credentials-cache/credentials.json` beside it. The directory must be writable
by the Mopidy service user. Newly created directories use mode `0700`, and
`auth.json` is atomically replaced with mode `0600`.

Check both credential sets independently:

```sh
mopidy spotify auth status
```

Running bare `mopidy spotify auth` displays the available authorization
commands. It is reserved for eventually running both authorization flows.

Legacy bridge credentials remain supported for existing installations:

```ini
[spotify]
client_id = ... client_id value you got from mopidy.com ...
client_secret = ... client_secret value you got from mopidy.com ...
```

Authentication is selected in this order:

1. A valid local PKCE authorization is preferred.
2. If local authorization is absent or cleared, configured bridge credentials
   are used.
3. An expired or revoked PKCE refresh token requires running
   `mopidy spotify auth web` again. It does not silently fall back to the bridge.
4. Corrected bridge credentials are retried after a bridge authorization error.

Run `mopidy spotify logout` to clear both stored credential sets: librespot
playback credentials and local Web API PKCE authorization. Configured legacy
bridge credentials are not stored credentials and remain available for Web API
fallback. Reauthorize each local flow with its corresponding command.

The following configuration values are available:

- `spotify/enabled`: If the Spotify extension should be enabled or not.
  Defaults to `true`.

- `spotify/client_id`: Legacy Mopidy bridge client ID. Optional when local PKCE
  authorization is configured.

- `spotify/client_secret`: Legacy Mopidy bridge secret. Optional when local PKCE
  authorization is configured.

- `spotify/bitrate`: Audio bitrate in kbps. `96`, `160`, or `320`.
  Defaults to `160`.

- `spotify/volume_normalization`: Whether volume normalization is active or
  not. Defaults to `true`.

- `spotify/timeout`: Seconds before giving up waiting for search results,
  etc. Defaults to `10`.

- `spotify/allow_cache`: Whether to allow caching. The cache is stored in a
  "spotify" directory within Mopidy's `core/cache_dir`. Defaults to `true`.

- `spotify/cache_size`: Maximum cache size in MiB. Set to `0` for unlimited. Defaults to `8192`.

- `spotify/allow_playlists`: Whether or not playlists should be exposed.
  Defaults to `true`.

- `spotify/search_album_count`: Maximum number of albums returned in search
  results. Number between 0 and 50. Defaults to 20.

- `spotify/search_artist_count`: Maximum number of artists returned in search
  results. Number between 0 and 50. Defaults to 10.

- `spotify/search_track_count`: Maximum number of tracks returned in search
  results. Number between 0 and 50. Defaults to 50.

- `spotify/username`: Deprecated since v5.0.0. Please remove from your configuration file.

- `spotify/password`: Deprecated since v5.0.0. Please remove from your configuration file.

## Project resources

- [Source code](https://github.com/mopidy/mopidy-spotify)
- [Issues](https://github.com/mopidy/mopidy-spotify/issues)
- [Releases](https://github.com/mopidy/mopidy-spotify/releases)
- [Authentication architecture](docs/authentication.md)

## Development

### Set up development environment

Clone the repo using, e.g. using [gh](https://cli.github.com/):

```sh
gh repo clone mopidy/mopidy-spotify
```

Enter the directory, and install dependencies using [uv](https://docs.astral.sh/uv/):

```sh
cd mopidy-spotify/
uv sync
```

### Running tests

To run all tests and linters in isolated environments, use
[tox](https://tox.wiki/):

```sh
tox
```

To only run tests, use [pytest](https://pytest.org/):

```sh
pytest
```

To format the code, use [ruff](https://docs.astral.sh/ruff/):

```sh
ruff format .
```

To check for lints with ruff, run:

```sh
ruff check .
```

To check for type errors, use [pyright](https://microsoft.github.io/pyright/):

```sh
pyright .
```

### Making a release

To make a release to PyPI, go to the project's [GitHub releases
page](https://github.com/mopidy/mopidy-spotify/releases)
and click the "Draft a new release" button.

In the "choose a tag" dropdown, select the tag you want to release or create a
new tag, e.g. `v0.1.0`. Add a title, e.g. `v0.1.0`, and a description of the changes.

Decide if the release is a pre-release (alpha, beta, or release candidate) or
should be marked as the latest release, and click "Publish release".

Once the release is created, the `release.yml` GitHub Action will automatically
build and publish the release to
[PyPI](https://pypi.org/project/mopidy-spotify/).

## Credits

- Original author: [Stein Magnus Jodal](https://github.com/jodal)
- Current maintainer: [Nick Steel](https://github.com/kingosticks)
- [Contributors](https://github.com/mopidy/mopidy-spotify/graphs/contributors)
