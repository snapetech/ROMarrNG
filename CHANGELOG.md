# Changelog

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
