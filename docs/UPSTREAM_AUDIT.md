# Upstream ROMarr backlog audit

Snapshot: 2026-10-12, BlizzHacker/romarr main `31fefb0330e995c00350546d1470e6dcfa0fe117`.
Scope: all 48 issues/PRs returned by the paginated GitHub API, including closed items:
25 issues and 23 PRs. Only #47 and #48 were open at snapshot time.
Machine-readable inventory: [upstream-audit.json](upstream-audit.json).
For the implementation summary, merge and test evidence, SeerrNG impact, and
remaining verification limits, see the [upstream implementation report](UPSTREAM_IMPLEMENTATION_REPORT.md).

“Existing coverage” means implementation and relevant regression coverage exist in this fork;
it does not mean this session recreated the reporter's deployment. “Implemented/adapted”
means this change fills a missing path or corrects a remaining defect. No issues were closed,
comments posted, or upstream PRs created. The completed work is submitted in the ROMarrNG fork.

## Changes and attribution

- Adapted upstream PR #45 / commit `706818b829e4ff3e82fdbbee7027e5b4868c03f4`
  (BlizzHacker, co-author badkid) for strict regions and selected translation languages.
  Preserved this fork's media-path editor and callback.
- Adapted upstream PR #46 / commit `050180f38b6e12c580aeceea3a7f89b385647439`
  (BlizzHacker, co-author badkid) for Hub acquisition. Added explicit sandbox opt-in,
  atomic ledger writes, cross-process serialization, retry replacement, stable job identities, isolated staging,
  output containment and failure visibility. The pinned Hub broker constructs its plugin
  environment from an allowlist; the adapter retains that broker boundary.
- Applied the fix described by PR #47 / issue #48 while integrating the UI; added a test
  that parses every rendered inline script with Node instead of only checking Python strings.
- Addressed PR #42 review findings: prefer active identity matches, refuse conflicting-ID
  title fallbacks, fulfil Wanted by the matched request, and use queued translation metadata.
- Completed a TitleDB-backed Collections path for #23: select title name/ID, kinds and
  latest/all listed versions; preview and batch requests use the same filtered plan.
  Switch request scoring enforces explicit IDs and version tags. Manual import exposes
  catalogue identification separately from checksum verification.
- SeerrNG DAT browsing and request selection use the same saved region/translation policy.
  The selected DAT variant is searched while preserving SeerrNG's stable title identity.
  Multiple requests sharing a transfer each receive completion state and imported assets;
  client IDs scope download identities so different clients cannot claim one another's jobs.
- TitleDB name loading reads the real eShop-keyed schema's `id` field. DLC families use
  the application's 0x2000 allocation; application-keyed patch history is exposed under
  the update ID. Base acquisition requests v0, independently of patch versions.
  Source data: [TitleDB US.en.json](https://github.com/blawar/titledb/blob/master/US.en.json)
  and [versions.json](https://github.com/blawar/titledb/blob/master/versions.json).
- Discord now sends the documented client User-Agent. This corrects a concrete API-contract
  mismatch relevant to the later 403 report on #33. It does not prove the cause of that
  installation's rejection. See [Discord's reference](https://docs.discord.com/developers/reference#user-agent).

## Per-item evidence

| Item | Request | Disposition | Implementation / regression evidence |
| --- | --- | --- | --- |
| [PR #1](https://github.com/BlizzHacker/romarr/pull/1) | Say which side of the volume mount has to match the download client | Existing coverage | README.md; tests/test_library.py |
| [Issue #2](https://github.com/BlizzHacker/romarr/issues/2) | Proxmox Script Error | Existing coverage | proxmox/ct; tests/test_installer.py |
| [PR #3](https://github.com/BlizzHacker/romarr/pull/3) | Default to port 6868, because 7878 is Radarr's | Existing coverage | tests/test_installer.py |
| [PR #4](https://github.com/BlizzHacker/romarr/pull/4) | Stop a path-mapping test failing on another thread's log | Existing coverage | tests/test_library.py |
| [PR #5](https://github.com/BlizzHacker/romarr/pull/5) | Every game, every platform: remove the disc-based exclusion | Existing coverage | tests/test_disc_platforms.py, test_disc_import.py |
| [PR #6](https://github.com/BlizzHacker/romarr/pull/6) | Set the standard: authenticate, index anything, and prove the file is right | Existing coverage | tests/test_auth_http.py, test_indexers.py, test_verified_import.py |
| [PR #7](https://github.com/BlizzHacker/romarr/pull/7) | Fix qBittorrent 5.x login and import all ROMs from multi-ROM archives | Existing coverage | tests/test_qbittorrent_login.py, test_multi_rom_import.py |
| [Issue #8](https://github.com/BlizzHacker/romarr/issues/8) | Error 401 (Unauthorized) - "Send your key as the X-Api-Key header" | Existing coverage | tests/test_first_run.py, test_auth_http.py |
| [PR #9](https://github.com/BlizzHacker/romarr/pull/9) | chore: add CodeRabbit configuration | Existing coverage | .coderabbit.yaml |
| [Issue #10](https://github.com/BlizzHacker/romarr/issues/10) | Plugins in the docker | Existing coverage | Dockerfile; tests/test_docker_install.py, test_plugin_sandbox.py |
| [Issue #11](https://github.com/BlizzHacker/romarr/issues/11) | Deluge Support | Existing coverage | romarr/downloaders.py (Deluge); tests/test_new_clients.py |
| [PR #12](https://github.com/BlizzHacker/romarr/pull/12) | Fix ROM Hub confinement in Docker | Existing coverage | tests/test_plugin_sandbox.py, test_docker_install.py |
| [PR #13](https://github.com/BlizzHacker/romarr/pull/13) | Fix empty plugin catalogue in Docker | Existing coverage | tests/test_docker_install.py |
| [PR #14](https://github.com/BlizzHacker/romarr/pull/14) | Fix expired qBittorrent sessions without a ROMarr restart | Existing coverage | tests/test_qbittorrent_login.py |
| [Issue #15](https://github.com/BlizzHacker/romarr/issues/15) | Docker plugin installs fail: missing git and invalid Archive.org v0.4.0 ref | Existing coverage | tests/test_docker_install.py, test_ui.py |
| [PR #16](https://github.com/BlizzHacker/romarr/pull/16) | Fix Docker plugin installation failures | Existing coverage | tests/test_docker_install.py, test_ui.py |
| [Issue #17](https://github.com/BlizzHacker/romarr/issues/17) | Inconsistant file permissions between container and host | Existing coverage | docker/entrypoint.sh; tests/test_docker_install.py, test_library.py |
| [Issue #18](https://github.com/BlizzHacker/romarr/issues/18) | No Connection to GGRequestz | Existing coverage | tests/test_ggrequestz_docs.py, test_first_run.py |
| [PR #19](https://github.com/BlizzHacker/romarr/pull/19) | Fix GG Requestz request delivery setup | Existing coverage | tests/test_ggrequestz_docs.py |
| [PR #20](https://github.com/BlizzHacker/romarr/pull/20) | Preserve media bind-mount permissions | Existing coverage | tests/test_docker_install.py, test_library.py |
| [Issue #21](https://github.com/BlizzHacker/romarr/issues/21) | Zero DATs Loaded | Existing coverage | tests/test_dat_zip.py |
| [Issue #22](https://github.com/BlizzHacker/romarr/issues/22) | Decompression & validation for non-native files for DAT verification | Existing coverage | romarr/decompress.py; tests/test_decompress.py |
| [Issue #23](https://github.com/BlizzHacker/romarr/issues/23) | Solution for Switch catalogging? | Implemented/adapted | romarr/titled.py, app.py, selection.py, ui.py; tests/test_titled.py |
| [Issue #24](https://github.com/BlizzHacker/romarr/issues/24) | interactive search using hub with archive.org | Implemented/adapted | tests/test_hub_acquisition.py |
| [Issue #25](https://github.com/BlizzHacker/romarr/issues/25) | Allow removing a title from Wanted without importing it | Existing coverage | tests/test_wanted_removal.py |
| [Issue #26](https://github.com/BlizzHacker/romarr/issues/26) | Persist the download queue across restarts | Existing coverage | tests/test_queue_persistence.py |
| [Issue #27](https://github.com/BlizzHacker/romarr/issues/27) | Blocklist stalled or failed downloads and grab the next release | Existing coverage | tests/test_failed_download_handling.py |
| [PR #28](https://github.com/BlizzHacker/romarr/pull/28) | Persist the queue, allow dropping a request, and retire dead downloads | Existing coverage | tests/test_wanted_removal.py, test_queue_persistence.py, test_failed_download_handling.py |
| [PR #29](https://github.com/BlizzHacker/romarr/pull/29) | docs: describe failed-download handling, and cut 0.9.0 | Existing coverage | README.md; tests/test_failed_download_handling.py |
| [Issue #30](https://github.com/BlizzHacker/romarr/issues/30) | Unable to pull the docker image | Public manifests verified; fork references correct | docker-compose.yml; tests/test_fork_image.py |
| [Issue #31](https://github.com/BlizzHacker/romarr/issues/31) | GitHub Container Repository OCI Image is not found | Public manifests verified; fork references correct | docker-compose.yml; tests/test_fork_image.py |
| [PR #32](https://github.com/BlizzHacker/romarr/pull/32) | Changed repo name in docker-compose.yml | Public manifests verified; fork references correct | docker-compose.yml; tests/test_fork_image.py |
| [Issue #33](https://github.com/BlizzHacker/romarr/issues/33) | webhooks seem to be broken | Implemented/adapted | romarr/notify.py; tests/test_notify.py |
| [Issue #34](https://github.com/BlizzHacker/romarr/issues/34) | 1G1R collection planner ignores nested library layout (Structure B) | Existing coverage | tests/test_present_titles.py |
| [Issue #35](https://github.com/BlizzHacker/romarr/issues/35) | pip install playwright doesn't work in the unraid docker container | Existing coverage | Dockerfile.browser; tests/test_browser_musl.py |
| [PR #36](https://github.com/BlizzHacker/romarr/pull/36) | fix: Unraid browser edition, working connection tests, nested-library planner | Existing coverage | tests/test_present_titles.py, test_browser_musl.py, test_notify.py |
| [Issue #37](https://github.com/BlizzHacker/romarr/issues/37) | Collections: strict region filtering and configurable fan-translation languages | Implemented/adapted | tests/test_strict_regions.py |
| [Issue #38](https://github.com/BlizzHacker/romarr/issues/38) | Completed downloads never import when the torrent name differs from the indexer title (queue matches by name, not hash) | Implemented/adapted | tests/test_import_queue_identity.py |
| [Issue #39](https://github.com/BlizzHacker/romarr/issues/39) | RomM library goes unreadable ~30 min after start: expired token gets HTTP 500 from RomM 5.3.1, re-auth only triggers on 401 | Existing coverage | tests/test_romm_token_refresh.py |
| [Issue #40](https://github.com/BlizzHacker/romarr/issues/40) | Expose ROM Hub plugin search in Interactive Search (plugins can be enabled but are never used) | Implemented/adapted | tests/test_hub_acquisition.py |
| [Issue #41](https://github.com/BlizzHacker/romarr/issues/41) | hub.py sets ROM_HUB_ALLOW_UNSANDBOXED=1 unconditionally at import | Existing coverage | tests/test_plugin_sandbox.py, test_plugin_trust.py |
| [PR #42](https://github.com/BlizzHacker/romarr/pull/42) | fix(import): match finished downloads to the queue by id before title | Implemented/adapted | tests/test_import_queue_identity.py |
| [PR #43](https://github.com/BlizzHacker/romarr/pull/43) | fix(romm): re-authenticate when RomM 5.3.1 reports a dead token as HTTP 500 | Existing coverage | tests/test_romm_token_refresh.py |
| [PR #44](https://github.com/BlizzHacker/romarr/pull/44) | fix(hub): stop pinning ROM_HUB_ALLOW_UNSANDBOXED=1 at import | Existing coverage | tests/test_plugin_sandbox.py, test_plugin_trust.py |
| [PR #45](https://github.com/BlizzHacker/romarr/pull/45) | feat(collections): strict region filtering and configurable fan-translation languages | Implemented/adapted | tests/test_strict_regions.py |
| [PR #46](https://github.com/BlizzHacker/romarr/pull/46) | feat(hub): expose ROM Hub plugin search in Interactive Search with staged import | Implemented/adapted | tests/test_hub_acquisition.py |
| [PR #47](https://github.com/BlizzHacker/romarr/pull/47) | fix(ui): remove stray backslash line-continuations that break the web UI script | Implemented/adapted | tests/test_ui.py (rendered JavaScript parsed with Node) |
| [Issue #48](https://github.com/BlizzHacker/romarr/issues/48) | Dashboard is completely non-interactive: invalid JS line-continuation backslashes in ui.py break the inline script | Implemented/adapted | tests/test_ui.py (rendered JavaScript parsed with Node) |

## Limits and acceptance work

- #30/#31/#32: anonymous `latest` manifest requests returned HTTP 200 for both
  `ghcr.io/blizzhacker/romarr` and `ghcr.io/snapetech/romarrng` on 2026-10-12.
  The reported denial is not currently reproducible at the manifest level. Upstream
  digest: `sha256:1349b4034592e3e86cf8c583a7a03b28f0a1db5ec5508d73759a879f5bdd79fb`.
  Fork digest: `sha256:77db59a61d74c4072ebe4095932db09f43c167c069eaa28ded5bd33dc53cdb6c`.
  This was a registry read, not an image deployment or proof that every layer pulls.
- #33 needs the reporter's Discord endpoint/network to confirm their specific HTTP 403.
  Tests here use intercepted requests; no webhook messages were sent.
- Hub acquisition is proven with a real fixture plugin in both built Linux amd64 images,
  using the pinned Hub broker and sandbox, a local HTTPS source, declared credentials,
  a hash-verified plugin data asset, generated ROM bytes, and a folder library. Third-party
  source credentials, Unraid, Proxmox and production download services still require
  deployment-specific checks; the fixture does not claim to reproduce those installations.
- TitleDB is catalogue evidence, not byte-integrity evidence. Names are optional and
  require TITLED_NAMES=1; absent version history cannot establish a latest version.
  A requested version requires a matching `[vNUMBER]` release tag. Untagged releases
  are intentionally not treated as proof of that version.
- Closed PR #32 is not imported literally: its temporary owner rename is not an
  appropriate image namespace for this fork.

Confidence: high for inventory completeness at the snapshot and tested local behavior;
moderate for untested deployment behavior. This document is not a claim that upstream can
close every report without deployment checks or that maintainers must accept the changes.

## Validation

The final implementation head for ROMarrNG PR #15 was
`be7c7f053f2c448005fccc859439f627f38d0046`. Its isolated Python 3.13 full-suite
run completed with **2,317 passed, 3 skipped, and 1 network test deselected**.
Focused regressions, trusted-launcher contracts, the rendered JavaScript parser,
and release-note checks are listed in the
[implementation report](UPSTREAM_IMPLEMENTATION_REPORT.md).

Both `Dockerfile` (Alpine) and `Dockerfile.browser` (Debian) built for Linux amd64.
`scripts/prove_upstream_acquisition.py` passed in both images, proving sandbox socket
refusal, host credential isolation, plugin secret/asset resolution, brokered HTTPS,
strict DAT browsing, shared download import, and authenticated exact-byte delivery
for two SeerrNG requests. CI now runs that proof for both images before publication.

An isolated Chromium session exercised the Switch Collections controls, previewed
one base v0, changed the form after preview, and requested the original previewed
set successfully. The disposable browser and fixture server were stopped afterward.
Release-note metadata, all 48 unique inventory entries, and `git diff --check` passed.
The GitHub-hosted PR checks were still queued when the change merged; see the
implementation report and live [PR #15 check status](https://github.com/snapetech-org/ROMarrNG/pull/15).
