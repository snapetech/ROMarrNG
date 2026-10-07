# Security

ROMarr runs on home servers next to download clients, library servers and
private services, and it holds credentials for all of them. This document says
what it protects, what it does not, and how to report a problem.

It is written to be checkable. Where it claims a property, there is a test
named for it; where something is not protected, it says so plainly rather than
implying otherwise.

## Reporting a vulnerability

Report privately through GitHub's
[security advisories](https://github.com/snapetech/ROMarrNG/security/advisories/new).
Please do not open a public issue for anything exploitable.

Include what you were running, what you did, and what happened. A proof of
concept helps but is not required — a clear description of the mechanism is
enough to act on.

Expect an acknowledgement within a week. Fixes go to `main` with a regression
test, and the advisory is published once a release carrying the fix exists.
Credit is given unless you ask otherwise.

## Supported versions

Fixes land on `main` and in the next release. Only the latest release is
supported; there are no backports to older tags.

**Anything at or below `v0.7.0` has no authentication at all** — its API
answers whoever reaches the port, on a service that queues downloads and writes
to the filesystem. If you installed from a release tarball on or before
2026-08-02, upgrade. The Proxmox installer refuses to deploy a build without
`romarr/auth.py`, and so does its updater — an update that silently replaces an
authenticated build with an open one is worse than an install that does,
because the operator has already decided the thing is safe to leave running.

## What ROMarr is

An acquisition and automation service. It searches indexers, hands releases to
a download client, verifies finished files against No-Intro and Redump DATs,
and files them into a library server.

That means it is **administrator-facing software**. It deliberately reaches
arbitrary operator-supplied addresses — your Prowlarr, your qBittorrent, your
RomM — and most of them are on RFC1918 addresses. ROMarr does not and will not
block private-range destinations, because doing so would break its entire
purpose. The boundary that matters is not "which addresses may be reached" but
"who may ask ROMarr to reach them", which is authentication.

## Authentication

Required by default. There is no configuration mistake that produces an open
install; the only way off is explicit.

- A fresh install is **unclaimed**: the first visit to the web UI sets the
  password. `POST /api/v1/setup` is open only while unclaimed and answers `409`
  afterwards, so it is a one-shot rather than a standing unauthenticated
  password reset.
- Setting `ROMARR_PASSWORD` or your own `ROMARR_API_KEY` claims the install
  before it serves a request, leaving no unclaimed window. This is what a
  container template should do.
- Passwords are hashed with scrypt (N=2^14, r=8, p=1), never stored plaintext.
- Browsers hold an HMAC-signed session cookie: `HttpOnly`, `SameSite=Strict`,
  `Path=/`. `SameSite=Strict` is what stands in for CSRF tokens — another site
  cannot make an authenticated request even if it knows the URL. Set
  `ROMARR_COOKIE_SECURE=1` when every browser session uses HTTPS; leave it
  unset only for direct plain-HTTP LAN access.
- API clients present `X-Api-Key`, `Authorization: Bearer` or `?apikey=`. The
  query form exists for senders that cannot set headers; it will appear in
  proxy logs, so prefer a header.
- SeerrNG has a separate generated provider key, shown under Settings →
  General. It accepts header credentials on the integration API only. The
  main key remains valid for compatibility and still grants administrator
  access. The provider key is never accepted in a query string.
- TOTP (RFC 6238) gates interactive sign-in. It deliberately does not gate the
  API key: a script cannot be prompted, and a key is already high-entropy.
- Login, search, download, SeerrNG integration, and general API calls have
  separate per-address rate limits. Wrong login credentials return `401`
  without revealing which of password or key was wrong.
- A state file ROMarr cannot **read** stops it starting. This is an
  authentication property, not a housekeeping one, and it was got wrong: an
  unreadable `romarr.json` — the normal result of a root-owned file under a
  container running as `PUID` — used to be treated the same as a corrupt one,
  so ROMarr started from defaults and saved over it. The API key was
  regenerated, the history emptied, and **the install came back unclaimed**, so
  the next person to reach the port set the password. That was a configuration
  mistake that produced an open install, and the paragraph above was therefore
  not true. It is now two guards: the Docker entrypoint owns `/config`
  recursively and refuses to start if the state file is still unreadable, and
  the application refuses to start on an unreadable state file however it was
  launched. A file that is merely *unparseable* still falls back to defaults,
  because nothing in it can be handed back.

Exactly ten routes answer without a credential, and no others (this count is
asserted against the code, not maintained by hand):

| Route | Why |
|---|---|
| `/` | Serves the sign-in or setup screen when you are not signed in, the app when you are. |
| `/login` | The sign-in screen. It has to answer somebody holding nothing. |
| `/link` | Where a peering invitation link lands. A **constant page** — see below. |
| `/api/v1/login` | Exchanges a password or key for a session. |
| `/api/v1/setup` | First-run claim. Open only while unclaimed; `409` after. |
| `/api/health` | Container health checks have no credential to offer. |
| `/api/v1/connect/steam/return` | Steam's OpenID redirect. It *cannot* carry the session cookie — see below. |
| `/api/v1/peer/accept` | A peer redeeming an invitation you minted. Carries the one-time secret or the claim code. |
| `/api/v1/peer/shelf` | A peer reading what you share. Requires peer id + token. |
| `/api/v1/peer/netplay` | A peer proposing a session. Requires peer id + token. |

**The three peer routes are open to the *session* gate and closed to
everyone without a peer credential.** They are called by another server,
not by a person with a browser, so requiring the operator's session cookie
would make federation impossible. Each authenticates differently instead:

- `/api/v1/peer/accept` requires the **one-time invitation secret** you
  minted and sent out of band, or the **short claim code** that is the other
  half of the same invitation. Either way it is single-use and compared in
  constant time. Redeeming it does not grant access to anything — the peer is
  held **unconfirmed** until you confirm it, so a leaked invitation is
  recoverable rather than final. See *Invitation links and claim codes*.
- `/api/v1/peer/shelf` and `/api/v1/peer/netplay` require an
  `X-Peer-Id` + `X-Peer-Token` pair issued to exactly one peer, compared
  in constant time. An unconfirmed peer authenticates as nobody, and a
  confirmed peer with the default `scope: none` sees an empty shelf, so
  neither route leaks anything by existing.

**`/link` is open because it is a constant.** It takes no parameters, reads
no invitation, touches no state and returns identical bytes to every caller.
It has to be open because the person opening it is *somebody else's* operator,
who has no account here — that is the entire situation the page exists for.
There is nothing behind it to ask, so there is nothing it can be made to say.

### Invitation links and claim codes

An invitation comes in two halves and only one of them is a secret.

- **The link** — `https://your-server/link#i=<invite id>&n=<name>` — carries
  no credential. Everything identifying it is in the **fragment**, which a
  browser never puts on the wire: it does not reach the inviting server's
  access log, it is not in the `Referer` header of whatever the recipient
  clicks next, and the request a chat client makes to render a link preview
  fetches the bare path and learns nothing. Losing this link loses nothing.
- **The claim code** — eight characters, e.g. `K7RM-9TFQ` — is the credential,
  and it is deliberately *not* in the link. URLs go to places credentials must
  not: browser history, the address bar of a shared screen, sync services,
  proxy logs, link unfurlers. So the half that authorises is the half a person
  types, and it can travel by a second channel — voice, SMS, another app.

Eight characters is about forty bits, which is small, so three things carry
the weight instead of length:

1. **The code expires in 15 minutes**, where the invitation itself lives 24
   hours. A code that sits in a chat log all day is a credential sitting in a
   chat log all day. Minting another is one click.
2. **Five wrong codes destroy the invitation.** Guessing is bounded at five
   attempts per invitation, not per address, because rate-limiting by address
   is defeated by having more addresses.
3. **Redeeming still grants nothing.** A correctly guessed code produces a row
   on your Friends page marked *awaiting your confirmation*, and nothing else.
   This is the same mutual-confirmation step that makes a leaked long secret
   recoverable, and it is what makes a short code safe to use at all.

Burning an invitation is also the alarm: the friend it was meant for finds it
gone and tells you, which is how you learn somebody was guessing.

`/api/v1/peer/accept` returns the long peer token to whoever completes the
handshake. That caller has just proved it holds this exact single-use
invitation, and the token it receives opens nothing until you confirm the
peer. It is how a claim code becomes a durable credential — short code in,
long token out, once.

Revocation is one-sided and immediate: deleting a peer invalidates its
token without that peer's cooperation, and touches no other peer's.

Relationships are persisted under `_peers`, tokens included, so they survive
a restart. That table is removed from the config endpoint **by name**,
alongside `_api_key` and `_password_hash` — not by a leading-underscore rule,
because several `_`-prefixed settings (`_romm_url`, `_prowlarr_url`) are
deliberately shown, and such a rule would have hidden the wrong half and
served the tokens. A test asserts no peer token appears in that response.
Invitations are deliberately *not* persisted: they expire in 24 hours, and
keeping them across a restart would only widen the window a leaked one is
useful for. That applies doubly to the wrong-guess counter, which lives on the
invitation — a restart that resurrected an invitation would reset its budget.

`/api/health` returns one bit unauthenticated — it used to return library paths
and client URLs, which is what a health check does not need.

**The Steam return is open because it has to be, and carries its own
credential instead.** The session cookie is `SameSite=Strict`, so when Steam
redirects the browser back to ROMarr the browser deliberately withholds it and
the request arrives with nothing. Loosening the cookie to `Lax` would fix that
one flow by weakening every other route against cross-site requests, so it is
not done. Instead the start of the flow — `/api/v1/connect/steam`, which *is*
authenticated — mints a `state`: 24 bytes of `secrets.token_urlsafe`, single
use, expiring in ten minutes. The return leg is refused without a live one, so
possession of it stands in for the cookie, and it can only have come from a
signed-in session.

Two further checks apply before anything is connected: the identity Steam
asserts must match `https://steamcommunity.com/openid/id/<17 digits>` exactly,
and the whole assertion is posted back to Steam with `check_authentication` and
must come back `is_valid:true`. The parameters arrive through the user's
browser and are treated as attacker-controlled until Steam itself confirms
them.

### `ROMARR_AUTH=disabled`

Turns the gate off. **Anything reaching the port is then in, including a
request that bypassed your proxy.** If something in front already
authenticates, prefer `ROMARR_AUTH=forward`, which keeps that proxy as the
authority but verifies the request actually came through it.

Forward mode requires `ROMARR_TRUSTED_PROXIES`. Identity headers are only
believed from those CIDRs, checked against the socket peer address — never
against `X-Forwarded-For`, which anybody can set. Without the CIDR list,
forward auth would be a header anyone could send.

## Filesystem

ROMarr writes files whose names come from torrents, which are attacker
controlled.

- Every archive member is checked to resolve inside the destination before
  extraction — zip, 7z and rar alike. The check lives above the format
  readers, not inside the zip one, because the format an attacker picks is the
  one with the gap.
- Members failing the check are **dropped, not sanitised**: a release that
  needs sanitising is not one to trust.
- Multi-file sets are flattened to base names, so a set cannot traverse out of
  the directory it was given — safe by construction rather than by check.
- Existing files are never overwritten unless explicitly asked.
- Remote path mappings translate what a download client reports into what
  ROMarr can see. They are operator configuration, not attacker input.

## Secrets

- The config API masks every credential; a value is masked by field type, so a
  secret left behind after changing a provider's type is still masked.
- Backups exclude secrets unless `?secrets=1` is passed explicitly. This
  includes both API keys.
- The admin and SeerrNG keys are removed from `safe_settings`; neither
  unauthenticated page contains either key.
- Unexpected server errors return a generic response and log only the route
  and exception class, not a downstream exception string that might contain a
  credential-bearing URL.

## Plugins — read this before installing one

**ROM Hub plugins are code. Confinement is real but partial — read what it
does and does not cover before installing one.**

Each plugin runs as its own subprocess with no library token, no filesystem
mount of yours, and no network sockets of its own. Its only route outward is an
RPC back to ROMarr, which checks the destination against the hosts that plugin
declared in its manifest *before* opening a connection. A plugin that asks for
a host it did not declare is refused and the request never reaches the network.
A seccomp filter enforces this; it needs Linux and `pyseccomp`.

What that does **not** cover:

- A plugin runs arbitrary code in its subprocess and can read any file ROMarr
  can. Filesystem confinement needs a mount namespace and is not in place.
- Memory is not capped. The wall-clock timeout and output-size cap are.
- It can reach every host it declared. Read that list before installing; a
  search plugin asking for hosts unrelated to its source is the warning sign.

**If the filter cannot be installed, plugin operations stop.** ROMarr does not
silently run third-party code without its network/exec boundary. An operator
who accepts that risk can explicitly set
`ROMARR_ALLOW_UNSANDBOXED_PLUGINS=1`; ROMarr then logs the choice and sets the
Hub's `ROM_HUB_ALLOW_UNSANDBOXED=1` only for the plugin subprocess. The normal
Docker images include the runtime dependencies needed for the filter.

What *is* enforced:

- A plugin subprocess gets an **allowlisted** environment, not ROMarr's. It
  does not inherit `ROMARR_API_KEY`, `ROMARR_PASSWORD`, `PROWLARR_API_KEY`,
  `QBITTORRENT_PASS` or any other credential. It gets what a process needs to
  run, proxy settings, and the library credentials it needs to import — nothing
  else. An allowlist, because a denylist stops covering whatever is added next.
- Installing from a URL is checked against a host allowlist.
- Disabling a plugin removes it from every fan-out.

Treat installing a plugin as equivalent to running its author's code on your
server, because that is what it is.

## Dependencies

ROMarr's own code is Python standard library plus `requests`. The small
surface is deliberate: fewer dependencies is fewer supply-chain paths.

## What is not protected

Stated so nobody assumes otherwise:

- **No filesystem confinement for plugins.** Network and exec are
  confined; a plugin can still read any file ROMarr can. See above.
- **No protection against a malicious library or indexer you configured.**
  ROMarr trusts responses from services you pointed it at.
- **No encryption at rest.** `romarr.json` and `.env` hold credentials in
  plaintext; they are `chmod 600` and rely on filesystem permissions. A
  credential-inclusive exported backup can be passphrase-encrypted, but that
  does not encrypt the active state file.
- **No multi-user model.** There is one operator. Forward auth can require a
  group, but ROMarr does not distinguish users or keep per-user permissions.
- **No audit log of who did what**, because there is no "who".
- **Rate limits are local to one ROMarr process.** Login is limited to 5/min,
  search to 30/min, download actions to 60/min, SeerrNG integration to 120/min,
  and general API calls to 300/min per socket peer address. They are not a
  distributed quota or a defense against a large network-level flood.
- **Request workers and bodies are bounded.** The server accepts at most 64
  concurrent HTTP workers and times out idle socket reads after 30 seconds.
  JSON bodies are limited to 2 MiB, SeerrNG integration bodies to 64 KiB,
  capture uploads to 1 MiB, and restore payloads to 16 MiB. Four SeerrNG
  acquisitions may run at once; new work receives `503` plus `Retry-After`
  when all slots are busy.
- **The Sunshine admin API needs operator-supplied TLS trust.** Set
  `MOONLIGHT_TLS_CA_FILE` to a CA bundle or `MOONLIGHT_TLS_FINGERPRINT` to a
  SHA-256 certificate pin before ROMarr sends `MOONLIGHT_PASS`. A changed
  certificate stops the request. `MOONLIGHT_ALLOW_INSECURE_TLS=1` is an
  explicit compatibility override that disables peer verification; use it
  only on a trusted LAN with a unique Sunshine password. To read a pin from
  Sunshine's certificate, run
  `openssl s_client -connect sunshine-host:47990 -servername sunshine-host </dev/null 2>/dev/null | openssl x509 -noout -fingerprint -sha256`
  and set the output as `MOONLIGHT_TLS_FINGERPRINT`.
- **Wolf's underlying API remains full privilege.** ROMarr's client now
  allowlists four read endpoints and one pairing endpoint. A compromised
  ROMarr process that can open the Wolf socket still has access to Wolf's full
  API. Keep `WOLF_SOCKET_PATH` private to ROMarr or put `WOLF_API_URL` behind a
  private proxy that allows only those methods and paths; do not expose Wolf's
  API on a general network.
- **The Docker Compose example hardens the container** with a read-only root
  filesystem, `no-new-privileges`, all capabilities dropped except the three
  needed by the root entrypoint to own `/config` and switch to `PUID:PGID`, and
  a bounded no-exec `/tmp`. The mounted `/config`, ROM library and downloads
  remain writable for their stated purposes. Other deployment methods need
  equivalent settings applied by their operator.
- **Published container images carry signed provenance and SPDX SBOM
  attestations.** Verify an image with `gh attestation verify
  oci://ghcr.io/snapetech/romarrng:latest -R snapetech/ROMarrNG`. Attestations
  identify build origin and the SBOM; they do not prove the software is safe.
- **DAT verification is an integrity check, not a security control.** It tells
  you a file matches a known-good dump. It is not malware scanning, and an
  UNKNOWN verdict means "not in your DAT", not "dangerous".
