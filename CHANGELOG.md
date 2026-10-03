# Changelog

## [0.13.0] - 2026-10-03

### User-facing changes

#### Added

- **Browser Downloads:** ROMarrNG now publishes a Debian browser image with the Playwright client for sites that require a real browser. The browser server runs separately at the matching Playwright version; the default image and direct downloads are unchanged.
  - **Action required:** Use the ROMarrNG Browser template and configure a matching Playwright server for browser downloads.

#### Changed

- **Release Pipeline:** ROMarrNG release notes now include curated summaries and required upgrade actions, so people can see what changed without reading commit history.
- **Notifications:** The connection editor can test the values currently entered before saving and reports endpoint or network failure details. Masked secrets from saved connections are restored for the test when left unchanged.

#### Fixed

- **Collections:** The 1G1R collection planner now follows the configured library layout, including nested RomM libraries, so it recognizes games inside each platform's `roms` directory.

#### Security

- **Containers:** **Breaking:** The Docker Compose example now uses a read-only root filesystem, drops unnecessary capabilities, and enables no-new-privileges. Sunshine connections require a trusted CA or certificate pin; published images also carry signed provenance and SPDX SBOM attestations.
  - **Action required:** Configure MOONLIGHT_TLS_CA_FILE or MOONLIGHT_TLS_FINGERPRINT, or explicitly opt in to insecure TLS on a trusted LAN.
- **Integration:** SeerrNG can now use its own integration-only key. Concurrent submissions are deduplicated, request bodies and workers are bounded, and plugin operations stop when seccomp is unavailable unless an operator explicitly opts out.

## [0.12.3] - 2026-10-01

### User-facing changes

#### Fixed

- **Setup:** The setup guide now recognizes every configured download client. Users installing ROMarrNG alone or alongside SeerrNG will see an accurate status instead of a permanent “not set up” message.
  - **Action required:** Update ROMarrNG to the new release.

## [0.12.2] - 2026-10-01

ROMarrNG can now bind to a configured network address with `ROMARR_HOST`. The
container continues to listen on all interfaces; the YunoHost package binds
only to localhost so requests pass through YunoHost's access controls.

## [0.12.1] - 2026-10-01

The optional LaunchBox plugin and its proof harness now target
`net10.0-windows`, matching LaunchBox 14 and newer. Building the plugin requires
the .NET 10 SDK and the nonredistributable LaunchBox API assembly from the
operator's installation. The XML import path remains available for older
LaunchBox versions.

## [0.12.0] - 2026-10-01

### Added

- Remote download path mappings can target one configured download client. This
  lets SABnzbd and torrent clients use different local paths for the same
  reported remote path; existing mappings still apply to every client.

### Changed

- The Unraid Community Applications icon now displays the NG badge, with a
  refreshed cache version.
- Container images now use Python 3.14.

### Security

- Hardened Steam profile URL validation against untrusted destinations and
  made request-target credential redaction linear while preventing log-line
  injection. Removed attacker-controlled values from sensitive log messages.
- Enabled Dependabot updates and dependency review automation.

## [0.11.1] - 2026-09-29

The Unraid Community Applications template now uses the ROMarrNG 0.11.1 icon
cache version, allowing an older blank icon response to refresh.

## [0.11.0] - 2026-09-29

ROMarrNG's SeerrNG catalog endpoint can return the exact day-precision release
date for a requested IGDB platform. When IGDB has no complete date for that
platform, the endpoint returns `null` instead of using the game's global first
release date. Malformed and out-of-range platform IDs are rejected.

## [0.10.1] - 2026-09-28

This maintenance release republishes the verified ROMarrNG 0.10.0 codebase
with a new versioned image. It includes no application behavior changes.

## [0.10.0] - 2026-09-28

First GitHub Release for the existing ROMarrNG tag history through `v0.9.0`.
This version packages the fork's SeerrNG integration and the accumulated
improvements listed below.

ROMarrNG's update check now follows the Snapetech release feed, and this
release's versioned image is `ghcr.io/snapetech/romarrng:0.10.0`.

### Added

- SeerrNG can search ROMarrNG's game catalog, track acquisition requests, and
  retrieve request-scoped game files. Complete game archive downloads can
  resume after an interrupted transfer.
- The IGDB catalog can be filtered by platform, genre, and release year, and
  SeerrNG requests retain their catalog game and selected platform identity.
- Operators can check Prowlarr's management API and enabled indexer feeds
  separately when diagnosing search failures; diagnostics omit credentials and
  feed URLs.
- PS4, PS5, Vita, Xbox One, and Xbox Series requests can use the existing
  acquisition workflow for supported packages or folder dumps. In SeerrNG,
  assign these systems to **Modern** before requesting them.
- The Unraid Community Applications listing now has a ROMarrNG icon and
  setup guidance for storage paths and support. The icon URL is versioned so
  Community Applications can refresh a previously cached blank result.

### Fixed

- Incomplete multi-file imports and failed latest imports no longer make a game
  appear available or owned; successful retries restore ownership.
- New main-branch image builds supersede older runs, while versioned builds do
  not replace the `latest` image.
