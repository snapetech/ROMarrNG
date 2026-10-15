import hashlib
import json
from pathlib import Path

import pytest

from scripts.validation_engine.engine import export_receipt
from scripts.validation_engine.retain_failed_pytest_logs import stage_failed_pytest_logs


def _receipt(private_root, evidence, tasks):
    receipt = private_root / "romarr-validation" / "pytest.json"
    receipt.parent.mkdir()
    receipt.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "repository": "romarrng",
                "evidenceDirectory": str(evidence),
                "tasks": tasks,
            }
        ),
        encoding="utf-8",
    )
    return receipt


def test_only_receipt_verified_failed_task_logs_are_staged(tmp_path):
    private_root = tmp_path / "private"
    private_root.mkdir()
    evidence = private_root / "run-evidence"
    evidence.mkdir()
    failed_log = b"pytest failure details\n"
    passed_log = b"passed task output\n"
    (evidence / "failed.log").write_bytes(failed_log)
    (evidence / "passed.log").write_bytes(passed_log)
    receipt = _receipt(
        private_root,
        evidence,
        [
            {
                "taskId": "pytest-shard-a",
                "status": "failed",
                "exitCode": 1,
                "logFile": "failed.log",
                "logSha256": hashlib.sha256(failed_log).hexdigest(),
            },
            {
                "taskId": "pytest-shard-b",
                "status": "passed",
                "exitCode": 0,
                "logFile": "passed.log",
                "logSha256": hashlib.sha256(passed_log).hexdigest(),
            },
        ],
    )
    destination = private_root / "romarr-validation" / "failed-task-logs"

    staged = stage_failed_pytest_logs(receipt, private_root, destination)

    assert [task["taskId"] for task in staged] == ["pytest-shard-a"]
    assert (destination / "pytest-shard-a.log").read_bytes() == failed_log
    assert not (destination / "pytest-shard-b.log").exists()
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["failedTaskCount"] == 1
    assert manifest["tasks"][0]["logSha256"] == hashlib.sha256(failed_log).hexdigest()


def test_engine_exported_receipt_provides_evidence_for_failed_log_staging(tmp_path):
    private_root = tmp_path / "private"
    private_root.mkdir()
    evidence = private_root / "run-evidence"
    evidence.mkdir()
    log_contents = b"pytest failure details\n"
    (evidence / "pytest-shard-a.log").write_bytes(log_contents)
    receipt = private_root / "romarr-validation" / "pytest.json"
    failed_task = {
        "taskId": "pytest-shard-a",
        "status": "failed",
        "exitCode": 2,
        "logFile": "pytest-shard-a.log",
        "logSha256": hashlib.sha256(log_contents).hexdigest(),
    }

    export_receipt(
        {"schemaVersion": 2, "repository": "romarrng", "tasks": [failed_task]},
        str(receipt),
        evidence,
    )
    destination = private_root / "romarr-validation" / "failed-task-logs"
    staged = stage_failed_pytest_logs(receipt, private_root, destination)

    assert [task["taskId"] for task in staged] == ["pytest-shard-a"]
    assert (destination / "pytest-shard-a.log").read_bytes() == log_contents
    assert json.loads(receipt.read_text(encoding="utf-8"))["evidenceDirectory"] == str(
        evidence.resolve()
    )


def test_failed_task_log_digest_must_match_receipt(tmp_path):
    private_root = tmp_path / "private"
    private_root.mkdir()
    evidence = private_root / "run-evidence"
    evidence.mkdir()
    (evidence / "failed.log").write_text("changed after receipt", encoding="utf-8")
    receipt = _receipt(
        private_root,
        evidence,
        [
            {
                "taskId": "pytest-shard-a",
                "status": "failed",
                "exitCode": 1,
                "logFile": "failed.log",
                "logSha256": "0" * 64,
            }
        ],
    )

    with pytest.raises(ValueError, match="does not match its receipt digest"):
        stage_failed_pytest_logs(
            receipt,
            private_root,
            private_root / "romarr-validation" / "failed-task-logs",
        )


def test_evidence_directory_must_stay_inside_private_runner_storage(tmp_path):
    private_root = tmp_path / "private"
    private_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    receipt = _receipt(private_root, outside, [])

    with pytest.raises(ValueError, match="outside private temporary storage"):
        stage_failed_pytest_logs(
            receipt,
            private_root,
            private_root / "romarr-validation" / "failed-task-logs",
        )


def test_workflow_artifact_is_limited_to_receipt_and_failed_pytest_logs():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "docker.yml").read_text(
        encoding="utf-8"
    )
    test_job = workflow.split("  test:\n", 1)[1].split(
        "\n  validation-environment-portability:", 1
    )[0]

    assert "python3.13 -m scripts.validation_engine.retain_failed_pytest_logs" in test_job
    assert "romarr-validation/pytest.json" in test_job
    assert "romarr-validation/failed-task-logs/manifest.json" in test_job
    assert "romarr-validation/failed-task-logs/*.log" in test_job
    assert (
        "romarrng-validation-receipt-${{ github.run_id }}-${{ github.run_attempt }}"
        in test_job
    )
    assert "romarr-validation/**" not in test_job
