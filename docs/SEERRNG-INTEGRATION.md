# SeerrNG integration API

ROMarrNG is a separate acquisition service with an authenticated API for
SeerrNG. SeerrNG owns catalog discovery, approval, and the user-facing request
workflow; ROMarrNG searches configured sources, hands releases to a download
client, imports files, and reports request status.

All integration endpoints require ROMarrNG authentication. Call them from the
SeerrNG server using `X-Api-Key` or `Authorization: Bearer`. Keep the ROMarrNG
API key server-side.

## Handshake and platforms

`GET /api/v1/integration/ping` reports the service identifier, application
version, and request contract version. The current response uses
`service: "romarr"` for compatibility and `requestContractVersion: 1`.

`GET /api/platforms` is the authoritative list of importable systems. Each
entry includes the stable `slug`, display name, aliases, directory layout,
media details, supported extensions, size limit, and playability information.
Use aliases to map catalog platform names to ROMarrNG slugs. SeerrNG decides
which systems are requestable and whether each belongs to Retro or Modern.

`POST /api/v1/integration/library/lookup` accepts between 1 and 100
`{ "title": "...", "platform": "..." }` entries and returns whether those
games already exist in the configured library.

## Submit and read requests

`POST /api/v1/integration/requests` accepts a stable caller-owned request ID:

```json
{
  "externalRequestId": "seerrng:request:123",
  "game": "Chrono Trigger",
  "platform": "snes"
}
```

The first submission returns `202` while ROMarrNG processes the request. A
repeat submission with the same ID returns the existing record. The request ID
must contain 1 to 255 letters, digits, periods, underscores, colons, or hyphens;
the title is limited to 500 characters and the platform must resolve to a
supported system. Invalid input returns `400`.

`GET /api/v1/integration/requests/{externalRequestId}` returns the current
status, title, platform, whether imported files can be delivered, and a safe
error when the request failed. Status values include `searching`,
`downloading`, `available`, `failed`, and `cancelled`.

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
