# mopidy-spotify

[![Latest PyPI version](https://img.shields.io/pypi/v/mopidy-spotify)](https://pypi.org/p/mopidy-spotify)
[![CI build status](https://img.shields.io/github/actions/workflow/status/mopidy/mopidy-spotify/ci.yml)](https://github.com/mopidy/mopidy-spotify/actions/workflows/ci.yml)
[![Test coverage](https://img.shields.io/codecov/c/gh/mopidy/mopidy-spotify)](https://codecov.io/gh/mopidy/mopidy-spotify)

[Mopidy](https://mopidy.com/) extension for playing music from [Spotify](https://www.spotify.com/).

## Status

> [!WARNING]
> Spotify have recently disabled username and password login for playback
> ([#394](https://github.com/mopidy/mopidy-spotify/issues/394)) and we now use
> access token login. You no longer need to provide your Spotify account
> username or password.

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

- `gst-plugins-spotify`, the [GStreamer Rust Plugin]
  (https://gitlab.freedesktop.org/gstreamer/gst-plugins-rs) for Spotify
  playback, based on [librespot](https://github.com/librespot-org/librespot/).
  _This plugin is not yet available from apt.mopidy.com_. It must be either
  [built from source]
  (https://github.com/kingosticks/gst-plugins-rs-build/tree/main?tab=readme-ov-file#native-compile)
  or [Debian packages are available]
  (https://github.com/kingosticks/gst-plugins-rs-build/releases/latest)
  for some platforms.

**We currently require a forked version of this plugin which supports
token-based login.** This can be found
[here](https://gitlab.freedesktop.org/kingosticks/gst-plugins-rs/-/tree/spotify-access-token-logging).

Verify the GStreamer spotify plugin is correctly installed:

```sh
gst-inspect-1.0 spotifyaudiosrc | grep Version | awk '{print $2}'
```

## Installation

Install by running:

```sh
sudo python3 -m pip install --break-system-packages mopidy-spotify==5.0.0a3
```

## Configuration

Before starting Mopidy, you must visit https://mopidy.com/ext/spotify/#authentication
to authorize this extension against your Spotify account:

```ini
[spotify]
client_id = ... client_id value you got from mopidy.com ...
client_secret = ... client_secret value you got from mopidy.com ...
```

> [!IMPORTANT]
> Remove any `credentials.json` file you may have manually created.

The following configuration values are available:

- `spotify/enabled`: If the Spotify extension should be enabled or not.
  Defaults to `true`.

- `spotify/client_id`: Your Spotify application client id. You _must_ provide this.

- `spotify/client_secret`: Your Spotify application secret key. You _must_ provide this.

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

- `spotify/username`: Deprecated since v5.0.0a3.

- `spotify/password`: Deprecated since v5.0.0a3.

## Project resources

- [Source code](https://github.com/mopidy/mopidy-spotify)
- [Issues](https://github.com/mopidy/mopidy-spotify/issues)
- [Releases](https://github.com/mopidy/mopidy-spotify/releases)

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

Once the releease is created, the `release.yml` GitHub Action will automatically
build and publish the release to
[PyPI](https://pypi.org/project/mopidy-spotify/).

## Credits

- Original author: [Stein Magnus Jodal](https://github.com/mopidy)
- Current maintainer: [Nick Steel](https://github.com/kingosticks)
- [Contributors](https://github.com/mopidy/mopidy-spotify/graphs/contributors)
