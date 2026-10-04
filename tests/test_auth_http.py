"""The gate as a request actually meets it.

The unit tests prove `Auth` decides correctly. These prove the decision is
*applied* -- against a real socket, because a gate that is right in isolation
and unwired is exactly as open as no gate at all.
"""

from __future__ import annotations

import json
import io
import tarfile
import logging
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer

import pytest

from romarr.app import ROMarr, make_handler
from romarr.dat import parse_dat
from romarr.libraries import Game
from romarr.store import SeerrRequest

SEERR_CONTRACT_V2 = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "SEERRNG-INTEGRATION.contract-v2.json"
    ).read_text(encoding="utf-8")
)


@pytest.fixture
def server(tmp_path):
    """A live ROMarr on a loopback port, with auth on and a known key."""
    service = ROMarr({"ROMARR_DATA": str(tmp_path / "s.json"),
                      "ROMARR_API_KEY": "testkey"})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", service
    httpd.shutdown()
    httpd.server_close()


def get(url, key=None, cookie=None, method="GET", body=None, byte_range=None):
    request = urllib.request.Request(url, method=method)
    if key:
        request.add_header("X-Api-Key", key)
    if byte_range:
        request.add_header("Range", byte_range)
    if cookie:
        request.add_header("Cookie", cookie)
    if body is not None:
        request.add_header("Content-Type", "application/json")
        request.data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers


# --- the gate holds --------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/api/v1/game",
    "/api/v1/queue",
    "/api/v1/config",
    "/api/v1/system/status",
    "/api/platforms",
    "/api/queue",
])
def test_reading_anything_needs_a_key(server, path):
    base, _ = server
    code, _, _ = get(base + path)
    assert code == 401, f"{path} answered {code} with no key"


@pytest.mark.parametrize("path", [
    "/api/v1/game",
    "/api/v1/system/status",
    "/api/platforms",
])
def test_the_key_opens_it(server, path):
    base, _ = server
    code, _, _ = get(base + path, key="testkey")
    assert code == 200, path


def test_a_wrong_key_is_refused(server):
    base, _ = server
    code, _, _ = get(base + "/api/v1/game", key="wrong")
    assert code == 401


def test_internal_exception_details_are_not_returned_or_logged(server, caplog):
    base, service = server
    secret = "client-key-must-not-escape"

    def fail(*_args, **_kwargs):
        raise RuntimeError(f"downstream URL contained {secret}")

    service.search = fail
    code, body, _ = get(base + "/api/v1/search?game=Example", key="testkey")
    assert code == 500
    assert json.loads(body) == {"error": "internal server error"}
    assert secret not in caplog.text


def test_secure_cookie_flag_can_be_enabled_for_https_deployments(tmp_path):
    service = ROMarr({
        "ROMARR_DATA": str(tmp_path / "secure-cookie.json"),
        "ROMARR_API_KEY": "testkey",
        "ROMARR_COOKIE_SECURE": "1",
    })
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        _, _, headers = get(
            f"http://127.0.0.1:{httpd.server_address[1]}/api/v1/login",
            method="POST", body={"apikey": "testkey"})
        cookie = headers["Set-Cookie"]
        assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
        assert "Secure" in cookie
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_seerrng_library_lookup_is_bounded_and_distinguishes_partial_cache(server):
    base, service = server
    route = base + "/api/v1/integration/library/lookup"
    payload = {"titles": [
        {"title": "Super Metroid", "platform": "snes"},
        {"title": "Missing Game", "platform": "snes"},
    ]}
    code, _, _ = get(route, method="POST", body=payload)
    assert code == 401
    service._publish_library(
        [Game(id="1", name="Super Metroid", platform="snes")],
        "", partial=True)
    code, body, _ = get(route, key="testkey", method="POST", body=payload)
    assert code == 200
    result = json.loads(body)
    assert result == {"ready": True, "partial": True,
                      "matches": [{"title": "Super Metroid", "platform": "snes"}]}
    code, _, _ = get(route, key="testkey", method="POST",
                     body={"titles": [{"title": "x", "platform": "invalid"}]})
    assert code == 400


def test_seerrng_can_browse_and_request_a_dat_catalog_title(server, monkeypatch):
    base, service = server
    service.dats.add(parse_dat(
        '''<datafile><header><name>Nintendo - Super Nintendo Entertainment System</name><version>2025</version></header>
        <game name="Chrono Trigger (USA)"/><game name="Chrono Trigger (Europe)"/>
        <game name="Super Metroid (USA)"/>
        </datafile>'''
    ))
    code, body, _ = get(
        base + "/api/integration/seerrng/v1/ping",
        key=service.auth.integration_key,
    )
    assert code == 200
    handshake = json.loads(body)
    assert handshake["requestContractVersion"] == SEERR_CONTRACT_V2["requestContractVersion"]
    assert set(handshake["capabilities"]) == set(
        SEERR_CONTRACT_V2["handshake"]["capabilities"]
    )
    assert handshake["capabilities"]["datCatalog"] is True
    assert handshake["capabilities"]["emulationAcquisition"] is True

    code, body, _ = get(
        base + "/api/integration/seerrng/v1/catalog/dat/platforms",
        key=service.auth.integration_key,
    )
    assert code == 200
    assert json.loads(body)["results"][0]["slug"] == "snes"

    code, body, _ = get(
        base + "/api/integration/seerrng/v1/catalog/dat/browse-page?platformSlugs=snes&limit=1",
        key=service.auth.integration_key,
    )
    assert code == 200
    [game] = json.loads(body)["results"]
    assert game["catalogProvider"] == "dat"
    assert game["title"] == "Chrono Trigger"

    dispatched = threading.Event()
    monkeypatch.setattr(
        service,
        "request",
        lambda *_args, **_kwargs: (dispatched.set() or {"ok": False}),
    )
    payload = {
        "externalRequestId": "seerrng:dat:chrono-trigger",
        "game": game["title"],
        "platform": "snes",
        "identity": {
            "catalogProvider": "dat",
            "catalogKey": game["catalogId"],
            "platformSlug": "snes",
        },
    }
    code, body, _ = get(
        base + "/api/integration/seerrng/v1/requests",
        key=service.auth.integration_key,
        method="POST",
        body=payload,
    )
    assert code == 202
    request = json.loads(body)
    assert request["identity"]["catalogProvider"] == "dat"
    assert request["identity"]["catalogKey"] == game["catalogId"]
    assert "assets" not in request
    assert dispatched.wait(2)

    code, _, _ = get(
        base + "/api/integration/seerrng/v1/requests",
        key=service.auth.integration_key,
        method="POST",
        body=payload,
    )
    assert code == 200
    code, body, _ = get(
        base + "/api/integration/seerrng/v1/catalog/dat/search-page?q=Super%20Metroid&platformSlugs=snes",
        key=service.auth.integration_key,
    )
    assert code == 200
    [other_game] = json.loads(body)["results"]
    mismatch = {
        **payload,
        "game": other_game["title"],
        "identity": {
            "catalogProvider": "dat",
            "catalogKey": other_game["catalogId"],
            "platformSlug": "snes",
        },
    }
    assert get(
        base + "/api/integration/seerrng/v1/requests",
        key=service.auth.integration_key,
        method="POST",
        body=mismatch,
    )[0] == 409


def test_seerrng_scoped_key_cannot_read_the_admin_api(server):
    base, service = server
    key = service.auth.integration_key
    for path in ("/api/integration/seerrng/v1/ping",
                 "/api/v1/integration/ping"):
        assert get(base + path, key=key)[0] == 200
    assert get(base + "/api/v1/system/status", key=key)[0] == 401
    assert get(base + "/api/v1/system/status", key="testkey")[0] == 200
    assert get(base + "/api/v1/integration/ping?apikey=" + key)[0] == 401


def test_seerrng_key_can_be_revealed_and_rotated_by_the_operator(server):
    base, service = server
    old = service.auth.integration_key
    code, body, _ = get(base + "/api/v1/system/seerrng-key", key="testkey")
    assert code == 200
    assert json.loads(body)["api_key"] == old
    code, body, _ = get(base + "/api/v1/system/seerrng-key/rotate",
                        key="testkey", method="POST", body={})
    new = json.loads(body)["api_key"]
    assert code == 200 and new != old
    assert get(base + "/api/v1/integration/ping", key=old)[0] == 401
    assert get(base + "/api/v1/integration/ping", key=new)[0] == 200


def test_seerrng_request_admission_is_idempotent_under_concurrency(
    server, monkeypatch
):
    base, service = server
    monkeypatch.setattr(service, "library_view", lambda **_: {"items": []})
    dispatched = []

    def start(service, request):
        dispatched.append(request.external_request_id)
        service._seerr_dispatch_pool.release(request.external_request_id)

    monkeypatch.setattr("romarr.app._start_seerr_dispatch", start)
    url = base + "/api/integration/seerrng/v1/requests"
    payload = {"externalRequestId": "seerrng:race:1",
               "game": "Chrono Trigger", "platform": "snes"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(
            lambda _: get(url, key=service.auth.integration_key,
                          method="POST", body=payload), range(2)))
    assert sorted(reply[0] for reply in replies) == [200, 202]
    assert dispatched == ["seerrng:race:1"]
    assert len(service.store.seerr_requests) == 1


def test_seerrng_dispatch_limit_refuses_new_work_without_persisting_it(server):
    base, service = server
    busy = [f"already-running-{index}" for index in range(4)]
    assert all(service._seerr_dispatch_pool.reserve(value) for value in busy)
    try:
        code, _, headers = get(
            base + "/api/v1/integration/requests",
            key=service.auth.integration_key,
            method="POST",
            body={"externalRequestId": "seerrng:busy:1",
                  "game": "Chrono Trigger", "platform": "snes"},
        )
        assert code == 503
        assert headers["Retry-After"] == "15"
        assert service.store.get_seerr_request("seerrng:busy:1") is None
    finally:
        for value in busy:
            service._seerr_dispatch_pool.release(value)


def test_json_request_bodies_are_bounded_before_parsing(server):
    base, _ = server
    code, body, _ = get(
        base + "/api/v1/integration/library/lookup",
        key="testkey", method="POST",
        body={"titles": [{"title": "x" * 70000, "platform": "snes"}]},
    )
    assert code == 413
    assert json.loads(body)["error"] == "lookup body too large"

    code, body, _ = get(
        base + "/api/v1/config", key="testkey", method="PUT",
        body={"oversized": "x" * (2 << 20)},
    )
    assert code == 413
    assert json.loads(body)["error"] == "request body too large"


@pytest.mark.parametrize("framing", [
    b"Content-Length: nope\r\n",
    b"Content-Length: 0\r\nContent-Length: 0\r\n",
    b"Transfer-Encoding: identity\r\n",
])
def test_ambiguous_request_framing_closes_before_a_pipelined_request(
    server, framing
):
    _, service = server
    handler = make_handler(service)
    handler.protocol_version = "HTTP/1.1"
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    followup = (
        b"GET /api/v1/system/status HTTP/1.1\r\n"
        b"Host: localhost\r\nX-Api-Key: testkey\r\n"
        b"Connection: keep-alive\r\n\r\n"
    )
    request = (
        b"PUT /api/v1/config HTTP/1.1\r\n"
        b"Host: localhost\r\nX-Api-Key: testkey\r\n"
        b"Connection: keep-alive\r\n" + framing + b"\r\n" + followup
    )
    try:
        with socket.create_connection(httpd.server_address, timeout=3) as client:
            client.settimeout(3)
            client.sendall(request)
            client.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                chunk = client.recv(8192)
                if not chunk:
                    break
                chunks.append(chunk)
        response = b"".join(chunks)
        assert b"HTTP/1.1 400" in response
        assert response.count(b"HTTP/1.1 ") == 1
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_writing_needs_a_key(server):
    """The endpoints that matter most: these queue downloads and rewrite
    settings, and they were the ones answering anybody."""
    base, _ = server
    for method, path, body in [
        ("POST", "/api/v1/webhook", {"data": {"game_title": "x",
                                              "platforms": ["snes"]}}),
        ("PUT", "/api/v1/config", {"min_seeders": 5}),
    ]:
        code, _, _ = get(base + path, method=method, body=body)
        assert code == 401, f"{method} {path} answered {code}"


def test_ggrequestz_can_deliver_with_the_query_key(server):
    """GG Requestz can configure a URL but cannot add an authentication header."""
    base, service = server
    received = []
    called = threading.Event()

    def request(game, platform):
        received.append((game, platform))
        called.set()

    service.request = request
    payload = {
        "type": "game_request",
        "title": "New Game Request: Chrono Trigger",
        "data": {
            "request_id": 42,
            "game_title": "Chrono Trigger",
            "platforms": ["Super Nintendo"],
            "request_type": "game",
        },
    }
    code, body, _ = get(
        base + "/api/v1/webhook/ggrequestz?apikey=testkey",
        method="POST", body=payload,
    )

    assert code == 202
    assert json.loads(body)["accepted"] is True
    assert called.wait(2)
    assert received == [("Chrono Trigger", "snes")]


def test_ggrequestz_is_told_when_romarr_rejects_the_event(server):
    """The sender only checks HTTP status, so {ok:false} with 200 is a false success."""
    base, _ = server
    code, body, _ = get(
        base + "/api/v1/webhook/ggrequestz?apikey=testkey",
        method="POST",
        body={"type": "game_request", "data": {
            "game_title": "Halo", "platforms": ["Sega Nomad"]}},
    )

    assert code == 422
    result = json.loads(body)
    assert result["ok"] is False
    assert "Sega Nomad" in result["error"]


def test_the_query_key_never_enters_the_access_log(server, caplog):
    """The only auth GG Requestz can send is in a URL, which HTTP servers log."""
    base, service = server
    service.request = lambda *_: None
    caplog.set_level(logging.INFO, logger="romarr.app")

    code, _, _ = get(
        base + "/api/v1/webhook/ggrequestz?source=ggr&api%6Bey=testkey&retry=1",
        method="POST",
        body={"type": "game_request", "data": {
            "game_title": "Contra", "platforms": ["NES"]}},
    )

    assert code == 202
    assert "testkey" not in caplog.text
    assert "api%6Bey=[REDACTED]" in caplog.text
    assert "source=ggr" in caplog.text and "retry=1" in caplog.text


def test_a_401_says_how_to_authenticate(server):
    base, _ = server
    _, body, _ = get(base + "/api/v1/game")
    assert b"X-Api-Key" in body


# --- what stays open, and how little it says -------------------------------

def test_the_healthcheck_still_works_without_a_key(server):
    """The container HEALTHCHECK has no credential and must not need one."""
    base, _ = server
    code, body, _ = get(base + "/api/health")
    assert code == 200
    assert json.loads(body)["ok"] is True


def test_an_unauthenticated_healthcheck_gives_away_nothing(server):
    """It used to return library paths, client URLs and counts. A liveness
    probe needs one bit; anything more is free reconnaissance."""
    base, _ = server
    _, body, _ = get(base + "/api/health")
    payload = json.loads(body)
    assert set(payload) == {"ok"}


def test_an_authenticated_healthcheck_is_still_the_full_report(server):
    base, _ = server
    _, body, _ = get(base + "/api/health", key="testkey")
    payload = json.loads(body)
    assert "libraries" in payload and "platforms" in payload


def test_the_ui_shell_is_served_so_there_is_somewhere_to_log_in(server):
    base, _ = server
    code, body, _ = get(base + "/")
    assert code == 200 and b"<" in body


# --- logging in ------------------------------------------------------------

def test_the_key_can_be_exchanged_for_a_session(server):
    base, _ = server
    code, _, headers = get(base + "/api/v1/login", method="POST",
                           body={"apikey": "testkey"})
    assert code == 200
    cookie = headers.get("Set-Cookie", "")
    assert "romarr_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite" in cookie

    session = cookie.split(";")[0]
    code, _, _ = get(base + "/api/v1/game", cookie=session)
    assert code == 200, "the session it just issued must work"


def test_a_bad_login_is_refused_and_sets_no_cookie(server):
    base, _ = server
    code, _, headers = get(base + "/api/v1/login", method="POST",
                           body={"apikey": "wrong"})
    assert code == 401
    assert "romarr_session=" not in headers.get("Set-Cookie", "")


# --- the escape hatch, end to end ------------------------------------------

def test_auth_disabled_opens_everything_deliberately(tmp_path):
    service = ROMarr({"ROMARR_DATA": str(tmp_path / "s.json"),
                      "ROMARR_AUTH": "disabled"})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        assert get(base + "/api/v1/game")[0] == 200
        assert set(json.loads(get(base + "/api/health")[1])) != {"ok"}
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_a_key_is_generated_when_none_is_configured(tmp_path):
    """Secure by default. An install that is open until somebody reads the
    documentation is an install that is open."""
    service = ROMarr({"ROMARR_DATA": str(tmp_path / "s.json")})
    assert service.auth.enabled
    assert len(service.auth.api_key) >= 32


def test_the_generated_key_survives_a_restart(tmp_path):
    data = str(tmp_path / "s.json")
    first = ROMarr({"ROMARR_DATA": data}).auth.api_key
    second = ROMarr({"ROMARR_DATA": data}).auth.api_key
    assert first == second and first


def test_the_key_is_never_returned_by_the_config_endpoint(server):
    """It is a credential, and that endpoint feeds a browser page."""
    base, service = server
    _, body, _ = get(base + "/api/v1/config", key="testkey")
    assert b"testkey" not in body


# --- single sign-on, as a request meets it ---------------------------------

def _serve(service):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_address[1]}", httpd


def test_sso_accepts_an_identity_from_a_trusted_proxy(tmp_path):
    """127.0.0.1 is the peer for a loopback test, so trusting it here is the
    same arrangement an operator has with a proxy on the LAN."""
    service = ROMarr({"ROMARR_DATA": str(tmp_path / "s.json"),
                      "ROMARR_API_KEY": "k",
                      "ROMARR_AUTH": "forward",
                      "ROMARR_TRUSTED_PROXIES": "127.0.0.1/32"})
    base, httpd = _serve(service)
    try:
        request = urllib.request.Request(base + "/api/v1/game")
        request.add_header("X-authentik-username", "wade")
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 200
    finally:
        httpd.shutdown(); httpd.server_close()


def test_the_identity_header_alone_is_not_a_login(tmp_path):
    """The bypass this exists to close: with the peer outside every trusted
    range, `curl -H 'X-authentik-username: admin'` must be worth nothing."""
    service = ROMarr({"ROMARR_DATA": str(tmp_path / "s.json"),
                      "ROMARR_API_KEY": "k",
                      "ROMARR_AUTH": "forward",
                      # Loopback is deliberately NOT trusted here, so the
                      # test's own connection is an untrusted peer.
                      "ROMARR_TRUSTED_PROXIES": "10.99.99.0/24"})
    base, httpd = _serve(service)
    try:
        code, _, _ = get(base + "/api/v1/game")
        assert code == 401
        request = urllib.request.Request(base + "/api/v1/game")
        request.add_header("X-authentik-username", "admin")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                assert False, f"header alone was accepted: {response.status}"
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
    finally:
        httpd.shutdown(); httpd.server_close()


def test_the_api_key_still_works_alongside_sso(tmp_path):
    """A script cannot go through the browser's SSO flow, so the key has to
    keep working or every automation breaks the day SSO is turned on."""
    service = ROMarr({"ROMARR_DATA": str(tmp_path / "s.json"),
                      "ROMARR_API_KEY": "k",
                      "ROMARR_AUTH": "forward",
                      "ROMARR_TRUSTED_PROXIES": "10.99.99.0/24"})
    base, httpd = _serve(service)
    try:
        assert get(base + "/api/v1/game", key="k")[0] == 200
    finally:
        httpd.shutdown(); httpd.server_close()


def test_a_required_group_is_enforced_over_http(tmp_path):
    service = ROMarr({"ROMARR_DATA": str(tmp_path / "s.json"),
                      "ROMARR_API_KEY": "k",
                      "ROMARR_AUTH": "forward",
                      "ROMARR_TRUSTED_PROXIES": "127.0.0.1/32",
                      "ROMARR_SSO_GROUP": "romarr-admins"})
    base, httpd = _serve(service)
    try:
        for groups, expected in (("users|romarr-admins", 200), ("users", 401)):
            request = urllib.request.Request(base + "/api/v1/game")
            request.add_header("X-authentik-username", "wade")
            request.add_header("X-authentik-groups", groups)
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    assert response.status == expected, groups
            except urllib.error.HTTPError as exc:
                assert exc.code == expected, groups
    finally:
        httpd.shutdown(); httpd.server_close()


def test_login_requires_the_second_factor_when_one_is_enrolled(tmp_path):
    from romarr.totp import code_at, new_secret
    import time as _time

    secret = new_secret()
    service = ROMarr({"ROMARR_DATA": str(tmp_path / "s.json"),
                      "ROMARR_API_KEY": "k"})
    service.auth.password_hash = service.auth.hash_password("hunter2")
    service.auth.totp.secret = secret
    base, httpd = _serve(service)
    try:
        # Right password, no code.
        code, _, _ = get(base + "/api/v1/login", method="POST",
                         body={"password": "hunter2"})
        assert code == 401

        # Right password, right code.
        code, _, headers = get(base + "/api/v1/login", method="POST",
                               body={"password": "hunter2",
                                     "totp": code_at(secret, int(_time.time()))})
        assert code == 200
        assert "romarr_session=" in headers.get("Set-Cookie", "")
    finally:
        httpd.shutdown(); httpd.server_close()


# --- ops endpoints, as a request meets them --------------------------------

def test_metrics_needs_a_key_like_everything_else(server):
    """A metrics endpoint open while the rest of the app is not is a hole
    with a Grafana dashboard attached: it names every dependency, the queue
    depth and the library size."""
    base, _ = server
    assert get(base + "/metrics")[0] == 401

    code, body, _ = get(base + "/metrics", key="testkey")
    assert code == 200
    assert b"romarr_up 1" in body
    assert b"# TYPE romarr_platforms gauge" in body


def test_backup_omits_credentials_by_default(server):
    base, service = server
    service.store.settings["download_clients"] = [
        {"name": "q", "type": "qbittorrent", "password": "hunter2"}]
    _, body, _ = get(base + "/api/v1/backup", key="testkey")
    assert b"hunter2" not in body
    assert json.loads(body)["kind"] == "romarr-backup"


def test_backup_can_include_credentials_when_asked(server):
    base, service = server
    service.store.settings["download_clients"] = [
        {"name": "q", "type": "qbittorrent", "password": "hunter2"}]
    _, body, _ = get(base + "/api/v1/backup?secrets=1", key="testkey")
    assert b"hunter2" in body


def test_restore_rejects_something_that_is_not_a_backup(server):
    base, _ = server
    code, _, _ = get(base + "/api/v1/restore", key="testkey", method="POST",
                     body={"kind": "not-a-backup"})
    assert code == 400


def test_restore_round_trips_a_backup(server):
    base, service = server
    service.store.settings["min_seeders"] = 7
    _, backup, _ = get(base + "/api/v1/backup", key="testkey")
    service.store.settings["min_seeders"] = 1

    code, body, _ = get(base + "/api/v1/restore", key="testkey", method="POST",
                        body=json.loads(backup))
    assert code == 200
    assert service.store.settings["min_seeders"] == 7
    assert "password" in json.loads(body)["warning"].lower()


def test_export_offers_csv(server):
    base, _ = server
    code, body, headers = get(base + "/api/v1/export?what=wanted&format=csv",
                              key="testkey")
    assert code == 200
    assert "text/csv" in headers.get("Content-Type", "")


def test_an_unknown_export_is_refused(server):
    base, _ = server
    assert get(base + "/api/v1/export?what=nonsense", key="testkey")[0] == 400


def test_login_is_rate_limited(tmp_path):
    """The one endpoint where guessing is the attack, so it has to be limited
    for callers who have not authenticated -- which is all of them there."""
    service = ROMarr({"ROMARR_DATA": str(tmp_path / "s.json"),
                      "ROMARR_API_KEY": "k"})
    base, httpd = _serve(service)
    try:
        codes = [get(base + "/api/v1/login", method="POST",
                     body={"apikey": "wrong"})[0] for _ in range(12)]
        assert 429 in codes, codes
        limited = get(base + "/api/v1/login", method="POST",
                      body={"apikey": "wrong"})
        assert limited[2].get("Retry-After")
    finally:
        httpd.shutdown(); httpd.server_close()


def test_ordinary_browsing_is_not_rate_limited(server):
    base, _ = server
    codes = [get(base + "/api/v1/game", key="testkey")[0] for _ in range(20)]
    assert set(codes) == {200}


def test_complete_game_bundle_is_authenticated_and_request_scoped(server, tmp_path, monkeypatch):
    base, service = server
    root = tmp_path / "library"
    game = root / "ps5" / "Test Game"
    for number in range(120):
        path = game / "assets" / f"{number}.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"game")
    monkeypatch.setattr(service, "library_for", lambda _: ({"path": str(root)}, None))
    monkeypatch.setattr(service, "library_view", lambda **_: {"items": [
        {"id": str(game), "name": "Test Game", "platform": "ps5"},
    ]})
    service.store.put_seerr_request(SeerrRequest("seerr-1", "Test Game", "ps5"))
    service.store.put_seerr_request(SeerrRequest("seerr-2", "Other Game", "ps5"))
    route = base + "/api/v1/integration/requests/seerr-1/assets"
    assert get(route)[0] == 401
    status, body, _ = get(route, key="testkey")
    assert status == 200
    result = json.loads(body)
    assert result["bundleSupported"] is True
    [asset] = result["assets"]
    download = route + "/" + asset["id"]
    assert get(download)[0] == 401
    status, body, headers = get(download, key="testkey")
    assert status == 200
    assert headers["Content-Type"] == "application/x-tar"
    assert len(body) == asset["size"] == int(headers["Content-Length"])
    with tarfile.open(fileobj=io.BytesIO(body)) as archive:
        assert len(archive.getnames()) == 120
        assert archive.extractfile("assets/119.bin").read() == b"game"
    status, resumed, headers = get(download, key="testkey", byte_range="bytes=1024-2047")
    assert status == 206
    assert resumed == body[1024:2048]
    assert headers["Content-Range"] == f"bytes 1024-2047/{len(body)}"
    assert get(download, key="testkey", byte_range=f"bytes={len(body)}-")[0] == 416
    assert get(download.replace("seerr-1", "seerr-2"), key="testkey")[0] == 404


def test_seerr_request_views_do_not_return_host_paths(server, tmp_path, monkeypatch):
    base, service = server
    root = tmp_path / "private-library-root"
    asset = root / "snes" / "Chrono Trigger.sfc"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"rom")
    monkeypatch.setattr(service, "library_for", lambda _: ({"path": str(root)}, None))
    request = SeerrRequest(
        "seerrng:path-privacy",
        "Chrono Trigger",
        "snes",
        status="available",
        assets=[str(asset)],
    )
    service.store.put_seerr_request(request)

    for path in (
        "/api/v1/integration/requests",
        "/api/v1/integration/requests/current",
        "/api/v1/integration/requests/seerrng:path-privacy",
    ):
        code, body, _ = get(base + path, key=service.auth.integration_key)
        assert code == 200
        assert str(root).encode() not in body
        payload = json.loads(body)
        row = payload["requests"][0] if isinstance(payload, dict) and "requests" in payload else payload
        for field in SEERR_CONTRACT_V2["privacy"]["requestStatusForbiddenFields"]:
            assert field not in row
        assert row["deliverable"] is True


def test_generic_external_request_contract_coexists_with_seerrng(server):
    base, service = server
    dispatched = threading.Event()

    def request(game, platform, external_request_id=""):
        dispatched.set()
        return {"ok": False, "error": "no usable release"}

    service.request = request
    code, raw, _ = get(
        base + "/api/v1/integration/requests", key="testkey", method="POST",
        body={"name": "Chrono Trigger", "platform": "snes"},
    )
    assert code == 202
    created = json.loads(raw)
    assert created["request_id"].startswith("ext:")
    assert created["name"] == "Chrono Trigger"
    assert created["platform"] == "snes"
    assert dispatched.wait(2)

    code, raw, _ = get(
        base + "/api/v1/integration/requests/current", key="testkey")
    assert code == 200
    assert json.loads(raw)["request_id"] == created["request_id"]

    code, raw, _ = get(
        base + "/api/v1/integration/requests", key="testkey")
    assert code == 200
    assert json.loads(raw)["requests"][0]["request_id"] == created["request_id"]

    code, raw, _ = get(base + "/api/v1/integration/info", key="testkey")
    assert code == 200
    info = json.loads(raw)
    assert info["name"] == "ROMarrNG"
    assert info["supports_resume"] is True
