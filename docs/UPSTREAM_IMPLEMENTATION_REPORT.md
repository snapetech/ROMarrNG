# Upstream backlog implementation report

**Status checked:** 2026-10-12. This report describes work completed in the
ROMarrNG fork against [BlizzHacker/romarr](https://github.com/BlizzHacker/romarr)
at upstream `main` commit
[`31fefb0330e995c00350546d1470e6dcfa0fe117`](https://github.com/BlizzHacker/romarr/commit/31fefb0330e995c00350546d1470e6dcfa0fe117).
The complete point-in-time inventory is the
[upstream audit](UPSTREAM_AUDIT.md), with machine-readable data in
[upstream-audit.json](upstream-audit.json).

## Result and scope

The paginated GitHub inventory contained **48 items: 25 issues and 23 pull
requests**, including closed entries. The audit classifies 34 as already
covered by ROMarrNG implementation and regression tests, 11 as implemented or
adapted during this work, and 3 as public image-manifest checks where the fork's
references were correct. Only upstream PR #47 and issue #48 were open at the
snapshot; their broken-inline-JavaScript defect is fixed in ROMarrNG.

The implementation was merged into the Snapetech fork as
[ROMarrNG PR #15](https://github.com/snapetech-org/ROMarrNG/pull/15) on
2026-10-12. Its code head is `be7c7f053f2c448005fccc859439f627f38d0046`;
the fork's merge commit is `c55eeb6d2ca6bfc33725573692355d6451df6989`.
This makes the changes available for upstream review. It did not close issues,
change code, or create pull requests in BlizzHacker/romarr.

“Existing coverage” means the behavior and a relevant regression check were
already present in this fork; it does not prove the original reporter's exact
deployment. “Implemented/adapted” means the fork received a concrete code
change, with the per-item evidence in the audit. Manifest verification is
limited to anonymous registry manifest requests and does not prove every layer
pull or a successful deployment.

## What changed

| Upstream item | Fork behavior now documented and implemented | Main evidence |
|---|---|---|
| [Issue #23](https://github.com/BlizzHacker/romarr/issues/23), Switch cataloguing | Collections can plan Switch base games, updates, and DLC from TitleDB by title or ID; preview and batch acquisition use the same filtered plan. Name lookup is optional. Version-tagged release matching is explicit, and filename/version presence is not presented as checksum verification. | `romarr/titled.py`, `romarr/selection.py`, `tests/test_titled.py` |
| [Issue #24](https://github.com/BlizzHacker/romarr/issues/24), [PR #46](https://github.com/BlizzHacker/romarr/pull/46), Hub search and acquisition | Search-capable ROM Hub sources can return results to Interactive Search. Selected results stage through a ROM Hub download client and then enter ROMarr's normal import and verification path. The adapter has stable job identities, atomic ledger updates, cross-process serialization, bounded retry replacement, output containment, and visible failures. Unconfined execution still requires explicit operator opt-in. | `romarr/hub.py`, `tests/test_hub_acquisition.py`, `scripts/prove_upstream_acquisition.py` |
| [Issue #37](https://github.com/BlizzHacker/romarr/issues/37), [PR #45](https://github.com/BlizzHacker/romarr/pull/45), regions and translations | DAT 1G1R selection strictly filters disallowed regions and supports configured fan-translation languages, with the established preferred-region fallback and English behavior preserved. The same saved policy drives SeerrNG DAT browsing and acquisition. | `romarr/collections.py`, `tests/test_strict_regions.py`, `tests/test_translations_layout.py` |
| [Issue #38](https://github.com/BlizzHacker/romarr/issues/38), [PR #42](https://github.com/BlizzHacker/romarr/pull/42) review | Completed downloads match an active request by download identity before falling back to a title. Conflicting identities are not silently treated as title matches; the correct request is fulfilled using the queued translation metadata. | `romarr/app.py`, `romarr/selection.py`, audit references the related regression tests |
| [Issue #33](https://github.com/BlizzHacker/romarr/issues/33), Discord webhook | Requests send Discord's documented client User-Agent. This fixes a concrete API-contract mismatch relevant to the reported 403; the original endpoint and network were not available, so it does not establish that this was the reporter's only cause. | `romarr/downloaders.py`; see the audit's explicit reporter-specific limit |
| [PR #47](https://github.com/BlizzHacker/romarr/pull/47), [issue #48](https://github.com/BlizzHacker/romarr/issues/48), broken UI scripts | Invalid backslash line continuations were removed from rendered inline JavaScript. A regression test extracts and parses every rendered inline script with Node, rather than only inspecting Python source strings. | `romarr/ui.py`, `tests/test_ui.py` |
| [Issue #30](https://github.com/BlizzHacker/romarr/issues/30), [issue #31](https://github.com/BlizzHacker/romarr/issues/31), [PR #32](https://github.com/BlizzHacker/romarr/pull/32), image references | On 2026-10-12, anonymous `latest` manifest requests for both upstream and fork images returned HTTP 200. The temporary owner rename in PR #32 was not copied into the maintained fork namespace. | `docker-compose.yml`, `tests/test_fork_image.py`; this was a registry read, not a full deployment proof |

The audit table also records pre-existing fixes and coverage for installation,
authentication, DAT decompression, download clients, queue persistence,
failed-download replacement, path mapping, plugin packaging, and the other
reported items. Use that table rather than interpreting this summary as a
second independent issue inventory.

## SeerrNG integration

The backlog work follows the existing split of responsibilities: SeerrNG owns
catalog discovery and requester workflow; ROMarrNG searches, downloads,
imports, and reports delivery state. The
[integration guide](SEERRNG-INTEGRATION.md) is the API reference. In this
implementation, the important connections are:

- DAT browsing, platform counts, detail, and acquisition use one saved region
  and translation policy. A stable DAT catalog identity is retained while a
  selected variant is resolved; if it is no longer valid at dispatch, the
  request fails instead of silently switching games.
- Multiple caller-owned request IDs can share one download. Each request gets
  its own completion state and access to successfully imported assets, while
  downloader IDs are scoped to their configured client.
- Stable request IDs, idempotent creation, lifecycle actions, explicit retry
  handling after uncertain downloader handoff, and request-scoped streaming
  remain part of the versioned integration contract.
- Partial imports are not exposed as deliverable assets. Asset lookup checks
  that files still resolve under the configured library root and streams
  without returning local paths.

The HTTP contract and concurrency cases are exercised in
[`tests/test_auth_http.py`](../tests/test_auth_http.py). DAT catalog tests are
in [`tests/test_dat_catalog.py`](../tests/test_dat_catalog.py); persistence and
asset ownership coverage also appears in
[`tests/test_store.py`](../tests/test_store.py) and
[`tests/test_recent_consoles.py`](../tests/test_recent_consoles.py). The
packaged acquisition proof confirms two SeerrNG requests can share a Hub
transfer and stream the exact imported bytes.

## Security and validation work

The review expanded the plugin and validation boundaries while implementing
Hub acquisition:

- The plugin runtime uses an allowlisted process environment and keeps the
  ROM Hub broker as the only route for declared outbound hosts. Landlock limits
  filesystem access; seccomp blocks direct sockets, process execution,
  permission/ownership changes, child processes, and `io_uring` entry points
  while allowing ordinary threads. Plugin scratch is finite tmpfs with a
  per-file size bound. Confinement failure stops the operation unless the
  operator explicitly opts into unconfined plugins.
- The trusted local test launcher is offline, uses a preconfigured Python
  environment, and masks the checkout and neighboring workspace data from the
  test process. Its Linux boundary refuses unsupported privilege states and
  checks that process-dumpability can be restored. See the
  [validation-engine guide](development/validation-engine.md) and
  [security policy](../SECURITY.md).
- GitHub checkout steps no longer persist the workflow token in the checked-out
  repository configuration.

The distinction between the app's sandbox and its limits is in
[`SECURITY.md`](../SECURITY.md); concrete packaged checks are in
[`PROOF.md`](PROOF.md).

## Validation and hosted checks

The final implementation head received these local checks:

- Full isolated Python 3.13 suite: **2,317 passed, 3 skipped, 1 network test
  deselected**.
- Focused upstream/security regression selection: **26 passed, 1 skipped**.
- Trusted launcher contract: **2 passed**; it confirmed candidate code could
  not read checkout secrets or sibling workspace data.
- `scripts/prove_upstream_acquisition.py` passed in both packaged Docker image
  editions, with the standard container seccomp profile and with
  `seccomp=unconfined`. The proof checked socket and `io_uring` denial,
  protected-file metadata changes, child-process blocking, bounded scratch,
  host-credential isolation, brokered HTTPS, strict DAT selection, shared Hub
  download, and exact-byte streaming for two SeerrNG requests.
- The release-note tag contract passed for all **17 published ROMarrNG
  releases**. The rendered UI JavaScript parser and release-note metadata checks
  passed as well.

At merge time, GitHub-hosted PR checks were still queued: CodeQL, dependency
review, the Docker workflow's test and cross-platform validation jobs, the
packaged acquisition jobs, and the release-note contract. **Queued is not
passed.** The merge records the user's instruction and the local evidence; it
does not turn those remote results green. Current results are visible on
[PR #15](https://github.com/snapetech-org/ROMarrNG/pull/15) and its
[Docker workflow run](https://github.com/snapetech-org/ROMarrNG/actions/runs/38310170478).

## What remains to verify

- The inventory is a 2026-10-12 snapshot. New upstream issues and pull requests
  need a fresh paginated audit after the upstream baseline changes.
- No upstream issue was closed and no upstream pull request was opened. The
  upstream maintainers can review, request changes, or take none of this work.
- Registry manifest success does not prove that a reporter's Docker host can
  pull every image layer. A full image pull and the original deployment still
  require an environment that can reproduce them.
- The Discord User-Agent change satisfies the documented client contract, but
  the original 403 needs the reporter's webhook, account state, and network to
  verify the specific failure.
- Hub acquisition was proven with a fixture plugin in built Linux images. It
  does not stand in for every third-party source, credential, Unraid/Proxmox
  installation, or production download service.
- TitleDB name search is optional and requires `TITLED_NAMES=1`. TitleDB
  presence/version tags identify catalogue candidates; they are not checksums
  and do not establish that a ROM's bytes are correct.

These boundaries are part of the result. The goal was to make the upstream
requests actionable in this fork and leave enough evidence for maintainers and
reporters to decide what to adopt or verify next.
