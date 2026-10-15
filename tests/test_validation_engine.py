from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from scripts.validation_engine import config, engine
from scripts.validation_engine.engine import (
    ValidationError,
    acquire_lock,
    capture_candidate,
    create_plan,
    format_validation_progress,
    inherited_toolchain_environment,
    inventory_files,
    isolated_task_environment,
    parse_counts,
    release_lock,
    run_task,
    run_task_pool,
)
from scripts.validation_engine.reconcile import reconcile_receipts
from scripts.validation_engine import run_pytest_shard
from scripts.validation_engine.run_pytest_shard import shard_files
from scripts.validation_engine.trusted_sandbox import require_trusted_local_test_sandbox


def make_git_root(root: Path, files: dict[str, str]) -> Path:
    root.mkdir()
    for relative, contents in files.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(contents, encoding="utf-8")
    for command in (
        ["git", "init", "--quiet"],
        ["git", "config", "user.email", "validation@example.invalid"],
        ["git", "config", "user.name", "Validation Test"],
        ["git", "add", "--all"],
        ["git", "commit", "--quiet", "-m", "baseline"],
    ):
        subprocess.run(command, cwd=root, check=True, stdout=subprocess.DEVNULL)
    return root


def test_inventory_hashes_native_pytest_files_and_rejects_empty_or_duplicate_ownership(tmp_path: Path) -> None:
    root = make_git_root(tmp_path / "repo", {
        "requirements.txt": "requests\n",
        "tests/test_a.py": "def test_ok(): pass\n",
        "tests/helper.py": "def helper(): pass\n",
    })
    rules = [{"id": "pytest", "glob": "tests/test_*.py", "framework": "pytest", "owner": "unit"}]
    entries, counts = inventory_files(root, rules)
    assert counts == {"pytest": 1}
    assert entries[0]["file"] == "tests/test_a.py"
    assert len(entries[0]["sha256"]) == 64
    with pytest.raises(ValidationError, match="inventory is empty"):
        inventory_files(root, [{**rules[0], "glob": "tests/missing_*.py"}])
    with pytest.raises(ValidationError, match="duplicate ownership"):
        inventory_files(root, [rules[0], {**rules[0], "id": "second"}])


def test_candidate_digest_changes_when_tracked_or_untracked_source_changes(tmp_path: Path) -> None:
    root = make_git_root(tmp_path / "repo", {"requirements.txt": "pytest\n", "tests/test_a.py": "def test_ok(): pass\n"})
    inventory, _ = inventory_files(root, [{"id": "pytest", "glob": "tests/test_*.py", "framework": "pytest", "owner": "unit"}])
    before = capture_candidate(root, ["requirements.txt"], inventory)
    (root / "requirements.txt").write_text("pytest==9\n", encoding="utf-8")
    changed_tracked = capture_candidate(root, ["requirements.txt"], inventory)
    assert before["sourceSha256"] != changed_tracked["sourceSha256"]
    (root / "new_fixture.txt").write_text("new input\n", encoding="utf-8")
    changed_untracked = capture_candidate(root, ["requirements.txt"], inventory)
    assert changed_tracked["sourceSha256"] != changed_untracked["sourceSha256"]


def test_pytest_summary_counts_passed_skipped_failures_and_network_deselection() -> None:
    counts = parse_counts(
        {"id": "pytest-suite", "parser": "pytest"},
        "test output\n12 passed, 2 skipped, 7 deselected in 4.15s\n",
    )
    assert counts == {"passed": 12, "skipped": 2, "failed": 0, "excluded": 7}
    failed = parse_counts({"id": "pytest-suite", "parser": "pytest"}, "1 failed, 4 passed, 2 errors in 3s\n")
    assert failed["failed"] == 3


def test_live_progress_summary_reports_completed_and_active_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    tasks = [
        {"id": "passed", "name": "Passed task"},
        {"id": "blocked", "name": "Blocked task"},
        {"id": "running", "name": "Long task"},
    ]
    results = {
        "passed": {"status": "passed", "startedAt": "2026-10-12T00:00:00Z"},
        "blocked": {"status": "blocked"},
    }
    monkeypatch.setattr(engine.time, "monotonic", lambda: 100.0)
    assert format_validation_progress("sample", tasks, results, {"running": 35.0}) == (
        "[validation] sample: 1/3 selected tasks complete "
        "(1 passed, 0 failed, 1 blocked, 1 pending); running Long task (1m05s)"
    )


def test_live_progress_summary_lists_every_active_task(monkeypatch: pytest.MonkeyPatch) -> None:
    tasks = [
        {"id": "first", "name": "First shard"},
        {"id": "second", "name": "Second shard"},
    ]
    monkeypatch.setattr(engine.time, "monotonic", lambda: 120.0)
    assert format_validation_progress("sample", tasks, {}, {"first": 10.0, "second": 60.0}) == (
        "[validation] sample: 0/2 selected tasks complete "
        "(0 passed, 0 failed, 0 blocked, 2 pending); "
        "running First shard (1m50s), Second shard (1m00s)"
    )


def test_pytest_shards_cover_every_inventory_file_once() -> None:
    from scripts.validation_engine.engine import ROOT

    shards = [shard_files(ROOT, shard["letters"]) for shard in config.PYTEST_SHARDS]
    flattened = [relative for shard in shards for relative in shard]
    expected = sorted(path.relative_to(ROOT).as_posix() for path in ROOT.glob("tests/test_*.py"))
    assert sorted(flattened) == expected
    assert len(flattened) == len(set(flattened))
    assert [rule["id"] for rule in config.INVENTORY] == [f"pytest-shard-{item['id']}" for item in config.PYTEST_SHARDS]


def test_pytest_shard_selection_rejects_invalid_and_empty_shards(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unique lowercase filename letters"):
        shard_files(tmp_path, "aa")
    with pytest.raises(ValueError, match="unique lowercase filename letters"):
        shard_files(tmp_path, "A")
    with pytest.raises(ValueError, match="did not select any test files"):
        shard_files(tmp_path, "z")


def test_pytest_shard_runner_exposes_candidate_package_to_collection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "romarr"
    package.mkdir()
    (package / "__init__.py").write_text("ORIGIN = 'candidate-root'\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_runner.py").write_text("def test_placeholder(): pass\n", encoding="utf-8")
    repository_root = str(tmp_path.resolve())
    monkeypatch.setattr(run_pytest_shard, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "path", [
        entry for entry in sys.path if Path(entry or ".").resolve() != tmp_path.resolve()
    ])
    monkeypatch.delitem(sys.modules, "romarr", raising=False)
    imported: list[str] = []

    def collect_with_candidate_import_path(_args: list[str]) -> int:
        imported.append(importlib.import_module("romarr").ORIGIN)
        return 0

    monkeypatch.setattr(run_pytest_shard.pytest, "main", collect_with_candidate_import_path)

    assert run_pytest_shard.main(["r"]) == 0
    assert imported == ["candidate-root"]
    assert sys.path[0] == repository_root


def test_bounded_task_pool_runs_independent_tasks_concurrently() -> None:
    tasks = [
        {"id": f"shard-{index}", "stage": "repository", "concurrencyGroup": f"shard-{index}"}
        for index in range(4)
    ]
    barrier = threading.Barrier(2)
    active = 0
    maximum_active = 0
    lock = threading.Lock()

    def execute(task: dict) -> dict:
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        try:
            barrier.wait(timeout=5)
            return {"taskId": task["id"], "status": "passed"}
        finally:
            with lock:
                active -= 1

    results: dict[str, dict] = {}
    changed = run_task_pool(
        tasks,
        max_concurrent_tasks=2,
        results=results,
        execute_task=execute,
        check_source=lambda: True,
    )
    assert changed is False
    assert maximum_active == 2
    assert [results[task["id"]]["status"] for task in tasks] == ["passed"] * 4
    assert [results[task["id"]]["concurrencyGroup"] for task in tasks] == [task["id"] for task in tasks]


def test_bounded_task_pool_serializes_tasks_in_a_shared_concurrency_group() -> None:
    tasks = [
        {"id": "first", "stage": "repository", "concurrencyGroup": "shared"},
        {"id": "second", "stage": "repository", "concurrencyGroup": "shared"},
    ]
    active = 0
    maximum_active = 0
    lock = threading.Lock()

    def execute(task: dict) -> dict:
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        try:
            time.sleep(0.02)
            return {"taskId": task["id"], "status": "passed"}
        finally:
            with lock:
                active -= 1

    results: dict[str, dict] = {}
    run_task_pool(
        tasks,
        max_concurrent_tasks=2,
        results=results,
        execute_task=execute,
        check_source=lambda: True,
    )
    assert maximum_active == 1
    assert all(result["status"] == "passed" for result in results.values())


def test_bounded_task_pool_blocks_failed_dependencies_and_continues_independent_work() -> None:
    tasks = [
        {"id": "contract", "stage": "repository", "concurrencyGroup": "contract"},
        {"id": "dependent", "stage": "repository", "concurrencyGroup": "dependent", "dependsOn": ["contract"]},
        {"id": "independent", "stage": "repository", "concurrencyGroup": "independent"},
    ]
    started: list[str] = []
    results: dict[str, dict] = {}

    def execute(task: dict) -> dict:
        started.append(task["id"])
        return {"taskId": task["id"], "status": "failed" if task["id"] == "contract" else "passed"}

    run_task_pool(
        tasks,
        max_concurrent_tasks=2,
        results=results,
        execute_task=execute,
        check_source=lambda: True,
    )
    assert sorted(started) == ["contract", "independent"]
    assert results["dependent"]["status"] == "blocked"
    assert results["independent"]["status"] == "passed"


def test_bounded_task_pool_finishes_a_stage_before_starting_the_next() -> None:
    tasks = [
        {"id": "prepare-slow", "stage": "prepare", "concurrencyGroup": "slow"},
        {"id": "prepare-fast", "stage": "prepare", "concurrencyGroup": "fast"},
        {"id": "tests", "stage": "repository", "concurrencyGroup": "tests"},
    ]
    slow_started = threading.Event()
    fast_finished = threading.Event()
    release_slow = threading.Event()
    later_stage_started = threading.Event()
    started_too_early = []
    results: dict[str, dict] = {}

    def execute(task: dict) -> dict:
        if task["id"] == "prepare-slow":
            slow_started.set()
            if not release_slow.wait(timeout=5):
                raise TimeoutError("slow preparation did not finish")
        elif task["id"] == "prepare-fast":
            fast_finished.set()
        else:
            started_too_early.append(not release_slow.is_set())
            later_stage_started.set()
        return {"taskId": task["id"], "status": "passed"}

    def release_after_fast_prepare() -> None:
        assert slow_started.wait(timeout=5)
        assert fast_finished.wait(timeout=5)
        time.sleep(0.03)
        started_too_early.append(later_stage_started.is_set())
        release_slow.set()

    releaser = threading.Thread(target=release_after_fast_prepare)
    releaser.start()
    run_task_pool(
        tasks,
        max_concurrent_tasks=2,
        results=results,
        execute_task=execute,
        check_source=lambda: True,
    )
    releaser.join(timeout=5)
    assert not releaser.is_alive()
    assert started_too_early == [False, False]
    assert all(results[task["id"]]["status"] == "passed" for task in tasks)


def test_bounded_task_pool_invalidates_passes_when_source_changes() -> None:
    tasks = [
        {"id": "first", "stage": "repository", "concurrencyGroup": "first"},
        {"id": "second", "stage": "repository", "concurrencyGroup": "second"},
    ]
    source_checks = 0
    results: dict[str, dict] = {}

    def current_source() -> bool:
        nonlocal source_checks
        source_checks += 1
        return source_checks == 1

    changed = run_task_pool(
        tasks,
        max_concurrent_tasks=2,
        results=results,
        execute_task=lambda task: {"taskId": task["id"], "status": "passed"},
        check_source=current_source,
    )
    assert changed is True
    assert [results[task["id"]]["status"] for task in tasks] == ["blocked", "blocked"]


def test_parent_environment_stays_protected_until_all_concurrent_leases_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    monkeypatch.setattr(engine, "_hide_parent_environment", lambda: events.append("hide") or ("fake-libc", 1))
    monkeypatch.setattr(engine, "_restore_parent_environment", lambda state: events.append("restore"))
    first_started = threading.Event()
    second_started = threading.Event()
    release_first = threading.Event()
    release_second = threading.Event()

    def task(started: threading.Event, release: threading.Event) -> None:
        with engine._parent_environment_protection():
            started.set()
            if not release.wait(timeout=5):
                raise TimeoutError("task lease was not released")

    with engine._parent_environment_protection():
        first = threading.Thread(target=task, args=(first_started, release_first))
        second = threading.Thread(target=task, args=(second_started, release_second))
        first.start()
        second.start()
        assert first_started.wait(timeout=5)
        assert second_started.wait(timeout=5)
        release_first.set()
        first.join(timeout=5)
        assert not first.is_alive()
        assert events == ["hide"]
        release_second.set()
        second.join(timeout=5)
        assert not second.is_alive()
        assert events == ["hide"]
    assert events == ["hide", "restore"]


def test_local_test_execution_requires_matching_outer_sandbox_marker(tmp_path: Path) -> None:
    marker = tmp_path / "marker"
    token = "a" * 64
    with pytest.raises(RuntimeError, match="trusted bubblewrap launcher"):
        require_trusted_local_test_sandbox({}, marker)
    marker.write_text("b" * 64, encoding="utf-8")
    with pytest.raises(RuntimeError, match="trusted bubblewrap launcher"):
        require_trusted_local_test_sandbox({"VALIDATION_OUTER_SANDBOX_TOKEN": token}, marker)
    marker.write_text(token, encoding="utf-8")
    require_trusted_local_test_sandbox({"VALIDATION_OUTER_SANDBOX_TOKEN": token}, marker)
    require_trusted_local_test_sandbox({"GITHUB_ACTIONS": "true"}, marker)


def test_local_validation_refuses_dependency_install_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(ValidationError, match="Dependency installation is CI-only"):
        engine.main(["--task", "install-test-dependencies"])


def test_trusted_launcher_host_resource_canary() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable for the trusted-launcher canary")
    root = Path(__file__).resolve().parents[1]
    canary = root / "scripts/validation_engine/trusted-test-launcher.contract.mjs"
    result = subprocess.run(
        [node, "--test", str(canary)],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_validation_child_environment_uses_allowlist_and_private_directories(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    environment = isolated_task_environment(
        {
            "id": "fixture",
            "kind": "test",
            "env": {"FIXTURE_SETTING": "expected"},
        },
        run_root,
        {
            "PATH": "/toolchain/bin",
            "HOME": "/operator/home",
            "TMPDIR": "/operator/tmp",
            "PYTHONPATH": "/operator/python",
            "PIP_INDEX_URL": "https://user:secret@packages.invalid/simple",
            "GITHUB_TOKEN": "synthetic-token",
            "AWS_SECRET_ACCESS_KEY": "synthetic-secret",
            "RANDOM_PRIVATE_VALUE": "synthetic-private-value",
            "XDG_CONFIG_HOME": "/operator/config",
        },
    )
    environment_root = run_root / "fixture-environment"
    assert environment["PATH"] == "/toolchain/bin"
    assert environment["HOME"] == str(environment_root / "home")
    assert environment["USERPROFILE"] == environment["HOME"]
    assert environment["TMPDIR"] == str(environment_root / "tmp")
    assert environment["XDG_CONFIG_HOME"] == str(environment_root / "xdg-config")
    assert environment["XDG_CACHE_HOME"] == str(environment_root / "xdg-cache")
    assert environment["PIP_CACHE_DIR"] == str(environment_root / "pip-cache")
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert environment["CI"] == "true"
    assert environment["FIXTURE_SETTING"] == "expected"
    for key in ("PYTHONPATH", "PIP_INDEX_URL", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "RANDOM_PRIVATE_VALUE"):
        assert key not in environment
    with pytest.raises(ValidationError, match="unapproved inherited environment variable"):
        isolated_task_environment(
            {"id": "fixture", "kind": "test", "pass_env": ["GITHUB_TOKEN"]},
            run_root,
            {"GITHUB_TOKEN": "synthetic-token"},
        )
    with pytest.raises(ValidationError, match="unapproved inherited environment variable"):
        isolated_task_environment(
            {"id": "pytest-suite", "kind": "test",
             "pass_env": ["PIP_INDEX_URL"]},
            run_root,
            {"PIP_INDEX_URL": "https://packages.invalid/simple"},
        )
    with pytest.raises(ValidationError, match="safe lowercase identifier"):
        isolated_task_environment({"id": "../outside", "kind": "test"}, run_root, {"PATH": "/toolchain/bin"})
    if os.name != "nt":
        import stat

        assert stat.S_IMODE((environment_root / "home").stat().st_mode) == 0o700


def test_runtime_probe_environment_uses_the_toolchain_allowlist() -> None:
    environment = inherited_toolchain_environment({
        "PATH": "/toolchain/bin",
        "PYENV_ROOT": "/toolchain/pyenv",
        "PYTHONPATH": "/operator/python",
        "GITHUB_TOKEN": "synthetic-token",
        "HTTPS_PROXY": "http://proxy.invalid",
        "RANDOM_PRIVATE_VALUE": "synthetic-private-value",
    })
    assert environment == {
        "PATH": "/toolchain/bin",
        "PYENV_ROOT": "/toolchain/pyenv",
    }


def test_native_task_writes_private_log_and_records_result_counts(tmp_path: Path) -> None:
    task = {
        "id": "pytest-fixture",
        "kind": "test",
        "command": [sys.executable, "-c", "print('3 passed, 1 skipped, 2 deselected in 0.1s')"],
        "parser": "pytest",
        "minimum_cases": 1,
        "timeout_seconds": 10,
    }
    log = tmp_path / "pytest.log"
    result = run_task(tmp_path, task, log)
    assert result["status"] == "passed"
    assert result["activeCases"] == 3
    assert result["skippedCases"] == 1
    assert result["excludedCases"] == 2
    assert log.stat().st_mode & 0o777 == 0o600


def test_validation_task_streams_output_to_a_bounded_marked_log(tmp_path: Path) -> None:
    output_size = 16 * 1024 * 1024 + 1
    task = {
        "id": "output-limit-fixture",
        "kind": "setup",
        "command": [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(b'x' * " + str(output_size) + "); "
            "sys.stdout.write('VALIDATION_OUTPUT_COMPLETE')",
        ],
        "timeout_seconds": 30,
    }
    log = tmp_path / "bounded.log"
    result = run_task(tmp_path, task, log)
    contents = log.read_bytes()
    assert result["status"] == "passed"
    assert result["outputBytes"] == output_size + len("VALIDATION_OUTPUT_COMPLETE")
    assert len(contents) == 16 * 1024 * 1024
    assert contents.endswith(b"\n[validation log truncated after 16 MiB]\n")
    assert result["logSha256"] == hashlib.sha256(contents).hexdigest()


def test_validation_task_persists_output_before_timeout(tmp_path: Path) -> None:
    task = {
        "id": "timeout-log-fixture",
        "kind": "setup",
        "command": [
            sys.executable,
            "-c",
            "import sys, time; print('persisted-before-timeout', flush=True); time.sleep(10)",
        ],
        "timeout_seconds": 0.1,
    }
    log = tmp_path / "timeout.log"
    result = run_task(tmp_path, task, log)
    assert result["status"] == "failed"
    assert result["timedOut"] is True
    assert "persisted-before-timeout" in log.read_text(encoding="utf-8")


def test_validation_child_process_environment_is_allowlisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inherited = {
        "HTTPS_PROXY": "http://proxy.invalid:3128",
        "PIP_INDEX_URL": "https://user:pass@packages.invalid/simple",
        "PIP_EXTRA_INDEX_URL": "https://extra.invalid/simple",
        "PIP_TRUSTED_HOST": "packages.invalid",
        "PIP_CERT": "/operator/certs/pip-ca.pem",
        "REQUESTS_CA_BUNDLE": "/operator/certs/requests-ca.pem",
        "CURL_CA_BUNDLE": "/operator/certs/curl-ca.pem",
        "SSL_CERT_FILE": "/operator/certs/ssl-ca.pem",
        "SSL_CERT_DIR": "/operator/certs/ssl",
        "GITHUB_TOKEN": "synthetic-token",
    }
    # Clear case-insensitively first: on Windows deleting `https_proxy` after
    # setting `HTTPS_PROXY` removes that same environment entry.
    for name in set(inherited) | {
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    }:
        monkeypatch.delenv(name, raising=False)
    for name, value in inherited.items():
        monkeypatch.setenv(name, value)

    code = (
        "import json, os; keys = " + repr(list(inherited))
        + "; print(json.dumps({key: os.environ.get(key) for key in keys}))"
    )
    report = {}
    for task_id, pass_env in (
        ("install-test-dependencies", list(inherited)[:-1]),
        ("pytest-suite", []),
    ):
        task = {
            "id": task_id,
            "kind": "setup",
            "command": [sys.executable, "-c", code],
            "pass_env": pass_env,
            "timeout_seconds": 10,
        }
        log = tmp_path / f"{task_id}.log"
        result = run_task(tmp_path, task, log)
        assert result["status"] == "passed"
        report[task_id] = json.loads(log.read_text(encoding="utf-8"))

    for name, value in inherited.items():
        expected = None if name == "GITHUB_TOKEN" else value
        assert report["install-test-dependencies"][name] == expected
        assert report["pytest-suite"][name] is None


@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="PR_SET_DUMPABLE is Linux-specific")
def test_validation_task_cannot_read_runner_parent_environment(
    tmp_path: Path,
) -> None:
    helper = r'''
import sys
from pathlib import Path
from scripts.validation_engine.engine import run_task
run_root = Path(sys.argv[1])
run_root.mkdir(parents=True, exist_ok=True)
task_code = """from pathlib import Path\nimport os\npath = Path(f'/proc/{os.getppid()}/environ')\ntry:\n data = path.read_bytes()\nexcept PermissionError:\n print('PARENT_ENV_BLOCKED')\nelse:\n print('PARENT_ENV_CANARY_VISIBLE' if b'VALIDATION_PARENT_CANARY=parent-secret' in data else 'PARENT_ENV_READABLE')\n"""
task = {"id": "parent-env-probe", "kind": "setup",
        "command": [sys.executable, "-c", task_code], "timeout_seconds": 10}
result = run_task(Path.cwd(), task, run_root / "task.log")
print(result["status"])
print((run_root / "task.log").read_text())
'''
    environment = os.environ.copy()
    environment["VALIDATION_PARENT_CANARY"] = "parent-secret"
    result = subprocess.run(
        [sys.executable, "-c", helper, str(tmp_path / "nested-run")],
        cwd=Path(__file__).resolve().parents[1], env=environment,
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PARENT_ENV_BLOCKED" in result.stdout
    assert "PARENT_ENV_CANARY_VISIBLE" not in result.stdout
    assert "PARENT_ENV_READABLE" not in result.stdout


@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="PR_SET_DUMPABLE is Linux-specific")
def test_validation_runner_rejects_unrestorable_dumpable_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.validation_engine.engine as engine

    class FakePrctl:
        restype = None

        def __init__(self):
            self.calls = []

        def __call__(self, option, *args):
            self.calls.append(option)
            return 2 if option == 3 else 0

    class FakeLibc:
        def __init__(self):
            self.prctl = FakePrctl()

    libc = FakeLibc()
    monkeypatch.setattr(engine.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(engine.Path, "read_text",
                        lambda *args, **kwargs:
                        "CapEff:\t0000000000000000\n"
                        "CapPrm:\t0000000000000000\n")
    monkeypatch.setattr(engine.ctypes, "CDLL", lambda *args, **kwargs: libc)

    with pytest.raises(ValidationError, match="cannot be restored"):
        engine._hide_parent_environment()
    assert libc.prctl.calls == [3]


@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="CAP_SYS_PTRACE is Linux-specific")
def test_validation_runner_rejects_ptrace_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.validation_engine.engine as engine

    monkeypatch.setattr(engine.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(engine.Path, "read_text",
                        lambda *args, **kwargs:
                        "CapEff:\t0000000000080000\n"
                        "CapPrm:\t0000000000000000\n")
    with pytest.raises(ValidationError, match="CAP_SYS_PTRACE"):
        engine._hide_parent_environment()


def test_lock_rejects_overlap_and_never_deletes_a_replaced_lock(tmp_path: Path) -> None:
    first = acquire_lock(tmp_path)
    lock_path, content = first
    with pytest.raises(ValidationError, match="another validation run is active"):
        acquire_lock(tmp_path)
    lock_path.write_text('{"pid": -1}\n', encoding="utf-8")
    release_lock(first)
    assert lock_path.exists()
    lock_path.unlink()


def test_read_only_test_plan_discovers_repository_pytest_inventory() -> None:
    from scripts.validation_engine.engine import ROOT

    plan = create_plan(ROOT, {"tests_only": True})
    assert plan["selection"] == "tests-only"
    assert sum(plan["inventoryCounts"].values()) >= 100
    assert all(count > 0 for count in plan["inventoryCounts"].values())
    assert plan["tasks"][0]["selected"] is True
    assert plan["maxConcurrentTasks"] == 2
    test_tasks = [task for task in plan["tasks"] if task["kind"] == "test"]
    assert len(test_tasks) == len(config.PYTEST_SHARDS)
    assert all(task["selected"] and task["dependsOn"] == ["install-test-dependencies"] for task in test_tasks)
    assert len({task["concurrencyGroup"] for task in test_tasks}) == len(test_tasks)
    assert plan["runtimes"][0]["command"] == "python3.13"


def make_ci_receipt(run_attempt: str = "1") -> dict:
    sha = "a" * 40
    digest = "b" * 64
    counts = [27, 31, 25, 28]
    tasks = []
    inventory_counts = {}
    inventory_digests = {}
    for shard, count in zip(config.PYTEST_SHARDS, counts, strict=True):
        task_id = f"pytest-shard-{shard['id']}"
        inventory_counts[task_id] = count
        inventory_digests[task_id] = digest
        tasks.append({
            "taskId": task_id,
            "status": "passed",
            "activeCases": 25,
            "skippedCases": 1 if shard["id"] == config.PYTEST_SHARDS[0]["id"] else 0,
            "excludedCases": 10 if shard["id"] == config.PYTEST_SHARDS[0]["id"] else 0,
            "inventory": [{"lane": task_id, "discoveredFiles": count, "inventorySha256": digest}],
        })
    return {
        "schemaVersion": 2,
        "repository": "romarrng",
        "selection": "tests-only",
        "candidate": {"commit": sha, "tree": "c" * 40, "sourceSha256": "d" * 64, "inventorySha256": "e" * 64},
        "executionContext": {
            "executor": "github-actions",
            "nodeId": "romarrng-pytest-linux",
            "runner": {"name": "GitHub Actions 1", "os": "Linux", "architecture": "X64"},
            "github": {"runId": "41", "runAttempt": run_attempt, "sha": sha},
        },
        "status": "passed",
        "maxConcurrentTasks": config.MAX_CONCURRENT_TASKS,
        "inventoryCounts": inventory_counts,
        "inventoryLaneDigests": inventory_digests,
        "tasks": tasks,
        "totals": {"activeCases": 100, "skippedCases": 1, "excludedCases": 10},
        "completedAt": "2026-10-11T00:00:00+00:00",
    }


def test_receipt_reconciler_binds_run_attempt_source_and_inventory() -> None:
    receipt = make_ci_receipt()
    summary = reconcile_receipts([receipt], "41", "1", "a" * 40)
    assert summary["activeCases"] == 100
    assert summary["excludedCases"] == 10
    assert summary["inventoryFiles"] == 111
    with pytest.raises(ValidationError, match="different workflow run or attempt"):
        reconcile_receipts([receipt], "41", "2", "a" * 40)
    lane = f"pytest-shard-{config.PYTEST_SHARDS[0]['id']}"
    receipt["inventoryLaneDigests"][lane] = "f" * 64
    with pytest.raises(ValidationError, match="does not attest"):
        reconcile_receipts([receipt], "41", "1", "a" * 40)


def test_receipt_reconciler_requires_every_shard_to_pass() -> None:
    receipt = make_ci_receipt()
    receipt["tasks"].pop()
    with pytest.raises(ValidationError, match="every test shard"):
        reconcile_receipts([receipt], "41", "1", "a" * 40)
