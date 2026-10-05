# Remember rejected bridge credentials

A permanent bridge rejection blocks the credentials that failed, not future
configuration. `credential_fingerprint` stores a salted scrypt hash of that pair
in the error state:

- **Unchanged credentials:** report the saved error without contacting the bridge.
- **Changed client ID or secret:** allow another exchange. Success removes the
  fingerprint; another rejection replaces it.
- **Transient failure:** preserve the state so changed credentials can retry.
- **Legacy error without a fingerprint:** allow an exchange; a new rejection
  records the fingerprint.

Restart the backend to use configuration changes. Resetting authorization also
removes the fingerprint. Conditional writes prevent stale exchanges from
overwriting newer state.

## Why remember rejection?

Spotify's [six-month refresh-token expiration][expiration] applies to the user
grant behind the bridge, despite its client-credentials-style endpoint. Expiry
returns HTTP 400 with `invalid_grant`; refreshing access does not extend it.

Some older clients kept retrying rejected grants. The bridge's
[workaround][workaround] returns an invalid Bearer token with finite expiry to
selected User-Agents. The ensuing Web API 401 triggers those clients' backoff
instead. See also its [OAuth retry improvements][retries].

The fingerprint handles explicit token-endpoint rejection, not that workaround
or Web API 401/403 responses.

## Storage notes

Bridge credentials already exist in plaintext configuration. Scrypt is likely
overkill for generated secrets, but makes guessing from the stored hash more
expensive. The fingerprint is omitted from diagnostics and stored only in bridge error
state—not configured or PKCE state.

Old manifests remain readable. Clear or replace fingerprinted error state before
downgrading to a version that rejects the new field.

[expiration]: https://developer.spotify.com/blog/2026-06-18-refresh-token-expiration
[workaround]: https://github.com/adamcik/oauthclientbridge/commit/3e53b9bd884849c8d65703327d9706f1d2de88f4
[retries]: https://github.com/adamcik/oauthclientbridge/pull/90
