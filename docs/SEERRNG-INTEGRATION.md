# SeerrNG integration API

ROMarrNG is a separate acquisition service with an authenticated API for
SeerrNG. SeerrNG owns catalog discovery, approval, and the user-facing request
workflow; ROMarrNG searches configured sources, hands releases to a download
client, imports files, and reports request status.

Use the generated **SeerrNG provider key** from ROMarrNG's Settings → General
page in SeerrNG's provider settings. It accepts `X-Api-Key` or
`Authorization: Bearer` and is limited to the integration routes under either
prefix. It cannot read settings or call the rest of ROMarrNG's admin API. The
main API key continues to work for existing setups; rotate the provider key
from the same page, or set `ROMARR_SEERRNG_API_KEY` to manage it in the
environment. The provider key is never accepted in a query string.

The canonical SeerrNG prefix is `/api/integration/seerrng/v1`. The legacy
`/api/v1/integration` routes remain available for existing clients. SeerrNG
checks `requestContractVersion` in the handshake, uses the legacy routes when
an older ROMarrNG omits that field, and refuses contract versions it does not
understand.

Integration request bodies are limited to 64 KiB. ROMarrNG rate-limits
integration calls to 120 requests per minute per client address. At most four
SeerrNG acquisitions run at once; when full, a new request receives `503` and
`Retry-After: 15` without creating a request row. Request creation and retry
are idempotent under concurrent calls, so one external ID cannot launch two
searches.

## Handshake and platforms

`GET /api/v1/integration/ping` reports `service: "ROMarrNG"`, the application
version, API and request-contract versions, and capabilities. The `catalog`
capability is true when an IGDB metadata provider with credentials is
configured. Catalog requests return `503` when it is not configured.

`GET /api/platforms` is the authoritative list of importable systems. Each
entry includes the stable `slug`, display name, aliases, directory layout,
media details, supported extensions, size limit, and playability information.
Use aliases to map catalog platform names to ROMarrNG slugs. SeerrNG decides
which systems are requestable and whether each belongs to Retro or Modern.

`POST /api/v1/integration/library/lookup` accepts between 1 and 100
`{ "title": "...", "platform": "..." }` entries and returns whether those
games already exist in the configured library.

## Game catalog

The catalog endpoints use ROMarrNG's configured IGDB credentials. Catalog game
IDs are numeric IGDB IDs. Search and popular rows include a stable `id`
(`igdb-{id}`), `igdbId`, title, summary, cover URL, release date, platform
names and `{ id, name }` platform options, genres, rating, publishers,
developers, screenshots, and videos.

| Endpoint | Query | Response |
| --- | --- | --- |
| `GET /api/v1/integration/catalog/platforms` | — | IGDB platform `{ id, name }` rows |
| `GET /api/v1/integration/catalog/search` | `q` required; `limit` 1–50, default 20; optional `platformIds` as comma-separated IDs, `genre`, `releaseYear` | Search result array |
| `GET /api/v1/integration/catalog/search-page` | Same as search, plus `cursor` (default `0`) | `{ results, nextCursor }`; cursor is the next IGDB offset or `null` |
| `GET /api/v1/integration/catalog/popular` | `limit` 1–50, default 20; optional `offset` (0–10000), `platformIds`, `genre`, `releaseYear` | Popular result array |
| `GET /api/v1/integration/catalog/popular-page` | Same as popular | `{ results, nextOffset }`; next offset is a number or `null` |
| `GET /api/v1/integration/catalog/games/{igdbId}` | Positive numeric IGDB ID; optional positive `platformId` | One catalog title; `404` if missing. With `platformId`, includes `platformReleaseDate` for that exact platform, or `null` if IGDB has no day-precision release date |

Genre filtering is case-insensitive. Release years must be between 1950 and
2200. Search cursors and popular offsets are bounded to keep catalog requests
finite. A failed upstream catalog request returns a generic error without
exposing provider credentials or request details. Platform release dates never
fall back to the game's global first-release date.

## Submit and read requests

`POST /api/v1/integration/requests` accepts a stable caller-owned request ID:

```json
{
  "externalRequestId": "seerrng:request:123",
  "game": "Chrono Trigger",
  "platform": "snes",
  "identity": {
    "catalogProvider": "igdb",
    "catalogId": 1234,
    "platformId": 19
  }
}
```

`identity` is optional. When supplied, `catalogProvider` must be `igdb`,
`catalogId` must be a positive IGDB ID, and `platformId` is the selected IGDB
platform ID (or `0` when the target has no catalog platform ID). The request
ID must contain 1 to 255 letters, digits, periods, underscores, colons, or
hyphens; the title is limited to 500 characters and the platform must resolve
to a supported ROMarrNG system. Invalid input returns `400`.

The first submission returns `202` while ROMarrNG processes the request. A
repeat submission with the same ID returns the existing record only when its
normalized title, ROMarrNG platform, and catalog identity match. Reusing an ID
for another game or platform returns `409`.

If ROMarrNG restarts while a request is still searching, it changes that row
to `failed` so SeerrNG can offer a deliberate retry. If the process stopped
during download-client handoff, the separate confirmation requirement below
still applies because a transfer may already exist.

`GET /api/v1/integration/requests/{externalRequestId}` returns status, title,
platform, catalog identity when present, whether imported files can be
delivered, a safe failure message, and available `actions.retry` and
`actions.cancel` flags. Status values include `searching`, `downloading`,
`available`, `failed`, and `cancelled`.

## Retry and cancel

`POST /api/v1/integration/requests/{externalRequestId}/retry` retries a failed
request using its existing ID. Active or already available requests return
their current status. Cancelled requests cannot be retried. If the server
restarted during downloader handoff, first check the download client's queue
and history; retry only after confirming no matching transfer exists, and send:

```json
{ "confirmNoExistingDownload": true }
```

`POST /api/v1/integration/requests/{externalRequestId}/cancel` cancels a request
before ROMarrNG hands it to a downloader. Once a transfer is active, ROMarrNG
returns `409`; cancel it in the download client. An uncertain handoff also
requires explicit confirmation that no matching transfer exists.

## List and stream imported files

`GET /api/v1/integration/requests/{externalRequestId}/assets` lists files from
successful imports that still resolve beneath the configured library root.
The response includes opaque asset IDs, display names, sizes, and whether a
multi-file bundle is available. It does not expose filesystem paths.

`GET /api/v1/integration/requests/{externalRequestId}/assets/{assetId}` streams
an imported file or supported bundle. ROMarrNG checks the request and asset
again before opening it, refuses missing files and paths outside the configured
library root, and supports byte-range requests for resumable downloads.

SeerrNG should authorize access to its own request before calling either asset
endpoint, then proxy the stream without buffering the entire file. ROMarrNG
credentials and local paths stay server-side.

## Prowlarr diagnostics

`POST /api/v1/indexer/diagnose` separately checks Prowlarr's management API
and runs a bounded one-result search through each enabled torrent or usenet
feed. Results include the feed HTTP status, disabled-until time, and recent
failure detail when Prowlarr reports one. API keys and feed URLs are removed
from diagnostics. The Indexers page exposes the same check with per-indexer
results, which helps distinguish an invalid Prowlarr API key from an indexer
feed returning `401 Unauthorized`.
