# mopidy-spotify

[![Latest PyPI version](https://img.shields.io/pypi/v/mopidy-spotify)](https://pypi.org/p/mopidy-spotify)
[![CI build status](https://img.shields.io/github/actions/workflow/status/mopidy/mopidy-spotify/ci.yml)](https://github.com/mopidy/mopidy-spotify/actions/workflows/ci.yml)
[![Test coverage](https://img.shields.io/codecov/c/gh/mopidy/mopidy-spotify)](https://codecov.io/gh/mopidy/mopidy-spotify)

[Mopidy](https://mopidy.com/) extension for playing music from [Spotify](https://www.spotify.com/).

## Status

> [!WARNING]
> Library access and playback now require separate authorization. If playback
> has stopped working, run `mopidy spotify auth playback` as described under
> [Configuration](#configuration). Details at
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

- Mopidy >= 4.0. The music server that Mopidy-Spotify extends.

- `gst-plugins-spotify`, the
  [GStreamer Rust Plugin](https://gitlab.freedesktop.org/gstreamer/gst-plugins-rs) for Spotify
  playback, based on [librespot](https://github.com/librespot-org/librespot/).
  _This plugin is not yet available from apt.mopidy.com_. It must be either
  [built from source](https://github.com/kingosticks/gst-plugins-rs-build/tree/main?tab=readme-ov-file#native-compile)
  or
  [Debian packages are available](https://github.com/kingosticks/gst-plugins-rs-build/releases/latest)
  for some platforms.

  Choose a plugin package or source build that also installs `gstspotify-auth`,
  the helper required to authorize playback. Upstream releases through 0.15.4
  do not include it. See [helper availability](docs/authentication.md#playback-helper-availability).

**We currently prefer a forked version of this plugin which provides better logging.**
Details in release notes [here](https://github.com/kingosticks/gst-plugins-rs-build/releases/latest).

Verify the GStreamer spotify plugin is correctly installed:

```sh
gst-inspect-1.0 spotifyaudiosrc | grep Version | awk '{print $2}'
```

Check that the playback authorization helper is also installed:

```sh
command -v gstspotify-auth
```

If this prints nothing, install a plugin build that includes the helper before
continuing with playback authorization.

## Installation

Install by running:

```sh
sudo python3 -m pip install --break-system-packages mopidy-spotify
```

## Configuration

Before starting Mopidy, authorize both library access and playback. Run the
commands as the same operating-system user that runs Mopidy and with the same
configuration:

```sh
mopidy spotify auth web
mopidy spotify auth playback
```

If you run Mopidy as a system service, use these commands instead:

```sh
sudo mopidyctl spotify auth web
sudo mopidyctl spotify auth playback
```

`auth web` authorizes library access. Open the displayed URL, approve access in
Spotify, then paste the result shown by the browser into the terminal.

`auth playback` authorizes playback using the `gstspotify-auth` helper. Follow
its browser instructions. Authorizing library access does not authorize playback,
or vice versa.

> [!WARNING]
> The current playback helper prints an access token. Do not share its terminal
> output in logs or bug reports.

Library authorization is saved in your operating-system keyring when available.
Otherwise, the Web command warns before saving it in a local file protected by
file permissions. Use `mopidy spotify auth web --storage keyring` to require
keyring storage; see the [storage guide](docs/authentication.md#refresh-token-storage)
for installation and headless-service setup.

Check the saved authorization:

```sh
mopidy spotify auth status
```

For a system service, use `sudo mopidyctl spotify auth status`. Status reports
library access and playback separately. Playback `stored` means credentials are
saved; it does not check whether Spotify still accepts them.

Then start Mopidy. If library access expires or is revoked, run `auth web` again.
If playback needs reauthorization, run `auth playback` again. Use the same user
and configuration as during setup.

Run `mopidy spotify logout` (or `sudo mopidyctl spotify logout` for a system
service) to clear both library authorization and saved playback credentials.

### Migrating from the old setup

Existing `client_id` and `client_secret` settings in the `[spotify]` section
still work, but depend on an authentication server run by a Mopidy maintainer.
We recommend removing both settings and running `mopidy spotify auth web`
instead. Playback still requires its own authorization command.

Once authorized with the command, Mopidy keeps using that authorization even if
`client_id` and `client_secret` remain configured. If access expires or is revoked,
run the command again; Mopidy will not automatically switch back to the old
authentication server.

To switch back, run `mopidy spotify auth web --legacy`
(or `sudo mopidyctl spotify auth web --legacy` for a system service). This removes
local library authorization but leaves playback credentials unchanged. It records
your choice even if `client_id` and `client_secret` are missing, and warns you to
configure both. With both settings present, Mopidy uses the old authentication
server on the next token refresh; restart Mopidy to switch immediately.

Logout also permits using the old authentication server again. To stay logged
out instead, remove both settings as well.

See the [authentication docs](docs/authentication.md) for storage options and
troubleshooting.

If Mopidy reports invalid or unreadable authorization, run
`mopidy spotify auth web` again. It will not automatically use the old
authentication server instead. See [bridge rejection](docs/bridge-rejection.md)
for refresh-token expiry and the legacy-server workaround.

### Configuration values

The following configuration values are available:

- `spotify/enabled`: If the Spotify extension should be enabled or not.
  Defaults to `true`.

- `spotify/client_id`: Client ID for the old authentication server. We recommend
  removing this setting and using the authorization command above.

- `spotify/client_secret`: Client secret for the old authentication server. We
  recommend removing this setting and using the authorization command above.

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
