# Branch reconciliation — 2026-09-28

All remote work branches in the maintained ROMarrNG fork were reconciled onto
`main`. Each ref was either merged with its useful changes, already an ancestor
of `main`, or recorded below as superseded by newer mainline work. Old refs are
safe to delete after the main push.

## Feature and experiment outcomes

| Branch | Outcome on `main` |
|---|---|
| `feature/seerrng-request-assets` | Merged as `94e451f`. Its request and asset API had already evolved on `main` into the durable `SeerrRequest` flow with retry, cancellation, and path-checked file delivery. Kept the branch's integration documentation and rewrote it to match the maintained API. The older `IntegrationRequest` implementation was superseded. |
| `feat/disc-platforms` | Merged as `88fabd9`. The branch's 58-platform model is superseded by the current 79-platform catalogue, expanded playability model, and multi-file import logic. Main already installs `libarchive-tools` for `.7z` and `.rar` imports in both Docker and Proxmox. Kept the dated design and proof files as historical research. |
| `feat/arr-parity` | Merged as `7e2fd56` with the current tree retained. Its authentication, indexer drivers, verified imports, SSO/TOTP, profiles, notifications, download clients, metrics, exports, plugin catalogue, upgrades, and metadata capabilities are present in newer mainline implementations. Taking its old tree would remove current files and regress later fixes. |
| `contrib-test-backends` | Merged as `8018194`; added its pinned, throwaway Gaseous and Retrom fixtures in `da57609`. The branch's older library implementation was superseded by current `romarr/libraries.py`. Its dated 2026-07-29 report says Retrom passed all four backend calls; Gaseous passed reachability, count, and listing, while its rescan endpoint returned 404 and cover URLs remained unverified. Those are historical findings, not a result from this reconciliation. The fixture docs and sample password now use the ROMarr brand spelling checked by CI. |
| `feat/romarr-universal` | Already an ancestor of `main`; its work was already integrated. |

The disc-platform branch proved that the then-current emulator map covered 58
platforms. Main later expanded that model to 79 and added per-install player
capabilities, safer multi-file imports, and modern-console folder support. The
branch's smaller catalogue is no longer the source of truth.

## Older refs and duplicate fixes

| Ref(s) | Outcome |
|---|---|
| `backup/cdrive-20260919/claude/clever-haslett-a40ecf`, `backup/cdrive-20260919/main` | Both point to the same older Hub screenshot commit. Main already has the later screenshot from `f1e2e19`. |
| `backup/cdrive-20260919/master` | The Hub plugin browser is implemented in current mainline code (`romarr/hub.py`, routes, and UI). The branch's older implementation is superseded. |
| `backup/cdrive-20260919/codex/docker-plugin-catalog` | The image workflow now proves the bundled ROM Hub catalogue is non-empty and that a pinned plugin installs (`b92ea48`). The branch's catalogue fixes are superseded. |
| `backup/cdrive-20260919/codex/issue-15-docker-plugin-install` | Its commit is patch-equivalent to `00469b6`, which is already in main. |
| `backup/cdrive-20260919/codex/issue-17-permissions` | Its commit is patch-equivalent to `1b765ac`, which is already in main. |
| `backup/cdrive-20260919/codex/issue-18-ggrequestz`, `codex/issue-18-ggrequestz` | These refs point to the same tip. Request delivery is configured in main (`25b5f2c`), and query credentials including percent-encoded `api%6Bey` are redacted by `redact_query_credentials()`. |
| `backup/cdrive-20260919/pre-0.5.0-local` | Its unrelated 0.2-era baseline and tracker/platform fixes are superseded by the current indexer and platform implementations. Merged into main's history as `f5f261f`; no old tree was copied. |

The Unraid Community Apps icon is `packaging/unraid/icon.png`, referenced by
`packaging/unraid/romarrng.xml`.
The icon URL responds with the image, and the template release note is already
in `release-notes/2026-09-28-unraid-template-icon.md`.

## Release infrastructure

The repository has one configured remote, `origin`; there is no `upstream`
Git remote. Docker publication is owned by this fork's workflow and image name,
and the Proxmox installer fetches `snapetech/ROMarrNG`. The temporary local tag
`upstream-v0.9.0` is not a release tag and is removed during cleanup; published
`v0.3.0` through `v0.9.0` tags remain intact.

The live-backend fixture is maintainer tooling. It uses isolated disposable
containers, documents its historical result, and was not run during this
reconciliation.
