# Authorization terms

- **Bridge credentials**: The configured client ID and client secret used to
  request Web access through the legacy Mopidy OAuth bridge.
- **Credential fingerprint**: A stored value identifying the bridge credential
  pair associated with a permanent rejection, without containing the credential
  values. It distinguishes a retry of rejected credentials from an attempt with
  changed configuration.
- **Permanent bridge rejection**: A rejection that blocks further exchanges with
  the identified credential pair. It does not reject credentials supplied by a
  later configuration change.
