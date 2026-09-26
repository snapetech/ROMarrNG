# SeerrNG integration API

ROMarrNG is a separate acquisition service and fork of
[ROMarr](https://github.com/BlizzHacker/romarr). This contract is the fork's
SeerrNG integration surface; catalog discovery, approval, and the user-facing
request workflow remain in [SeerrNG](https://github.com/snapetech/seerrng).

All endpoints below require ROMarrNG authentication. SeerrNG should call them
server to server using `X-Api-Key` or `Authorization: Bearer`. Never put the
ROMarrNG API key in a browser response.

## Handshake

`GET /api/v1/integration/ping` returns the service name, ROMarrNG application
version, and `apiVersion`. SeerrNG must stop integration when it does not
support the returned contract version.

## Submit a request

`POST /api/v1/integration/requests`

```json
{
  "externalRequestId": "seerrng:request:123",
  "game": "Chrono Trigger",
  "platform": "snes"
}
```

`externalRequestId` is a stable caller-owned idempotency key. ROMarrNG stores
the request before starting the search. The first submission returns `202`;
an identical retry returns the same durable request record. If a service
restart leaves the request in `searching` with no queue item for that attempt,
replaying the request or reading its status resumes that pending attempt.
Persisted queue rows are used to reconcile download, import, and failure state
without dispatching the same recorded job again. Reusing an ID with a different
title or platform returns `409`. Unsupported or ambiguous platform names are
rejected rather than guessed.

ROMarrNG saves the request's handoff state before contacting the downloader.
If recovery finds a request in `downloading` or `importing` with no correlated
queue row, it marks the request failed with an uncertainty message instead of
automatically dispatching it again. This protects against duplicate jobs when
the downloader accepted work just before ROMarrNG stopped.

## Read status

`GET /api/v1/integration/requests/{externalRequestId}` returns the durable
request and one of these states:

| State | Meaning |
| --- | --- |
| `searching` | ROMarrNG is searching configured sources. |
| `downloading` | A release was handed to a configured download client. |
| `importing` | The completed download is being validated and filed. |
| `available` | At least one import succeeded. Check `deliverable` before offering a copy. |
| `failed` | Search, handoff, or import did not complete. |

Example response:

```json
{
  "externalRequestId": "seerrng:request:123",
  "game": "Chrono Trigger",
  "platform": "snes",
  "status": "available",
  "createdAt": "2026-09-25T12:00:00+00:00",
  "updatedAt": "2026-09-25T12:05:00+00:00",
  "deliverable": true
}
```

The response does not include provider credentials, local paths, release URLs,
or internal error details.

`POST /api/v1/integration/requests/{externalRequestId}/retry` retries a failed
request with its original ID. It returns `202` when a retry starts, `409` when
the request is not failed, and `404` when the ID is unknown. Repeating the
original `POST` reuses the durable request record and does not create another
request. When the status response includes an uncertain handoff error, inspect
the downloader's active queue and history first. Retry only after confirming
there is no matching download, and include this explicit confirmation:

```json
{
  "confirmNoExistingDownload": true
}
```

## List and stream imported files

`GET /api/v1/integration/requests/{externalRequestId}/assets` returns only
files recorded from successful imports and still present beneath their
configured library root:

```json
{
  "assets": [
    {
      "id": "opaque-id",
      "name": "Chrono Trigger (USA).sfc",
      "size": 4194304,
      "url": "/api/v1/integration/requests/seerrng%3Arequest%3A123/assets/opaque-id"
    }
  ],
  "bundleSupported": false
}
```

Paths are never returned. Each asset ID is scoped to its request and is resolved
again against ROMarrNG's configured library root immediately before opening the
file. Missing files, paths outside that root, and symlink escapes are refused.
The list contains individual imported files; ROMarrNG does not claim to bundle
multi-file or multi-disc sets in this contract version.

`GET /api/v1/integration/requests/{externalRequestId}/assets/{assetId}` streams
the file with `Content-Disposition: attachment`, `Cache-Control: no-store`,
and single-range byte requests for resumable transfers. The route returns
`404` when the request is not available or the asset no longer resolves.

SeerrNG must authorize access to its own request before it calls either asset
route, then proxy the byte stream without buffering the full file. The
request-scoped SeerrNG route is the user download link; ROMarrNG URLs and
credentials remain server-side.
