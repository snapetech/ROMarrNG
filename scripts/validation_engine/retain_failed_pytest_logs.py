"""Stage only receipt-verified failed pytest task logs for CI artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


def _contained(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def stage_failed_pytest_logs(
    receipt_path: Path, private_root: Path, destination: Path
) -> list[dict[str, Any]]:
    """Copy failed task logs after validating every path and recorded digest."""
    if private_root.is_symlink():
        raise ValueError("Private temporary storage must not be a symlink.")
    private = private_root.resolve(strict=True)
    if not private.is_dir():
        raise ValueError("Private temporary storage is not a directory.")
    if receipt_path.is_symlink():
        raise ValueError("The validation receipt must not be a symlink.")
    receipt = receipt_path.resolve(strict=True)
    expected_destination = private / "romarr-validation" / "failed-task-logs"
    if not _contained(receipt, private) or receipt == private:
        raise ValueError("The validation receipt is outside private temporary storage.")
    if destination.resolve(strict=False) != expected_destination:
        raise ValueError("The failed-log destination is not the fixed artifact directory.")

    report = json.loads(receipt.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("schemaVersion") != 2:
        raise ValueError("The validation receipt has an unsupported schema.")
    evidence_value = report.get("evidenceDirectory")
    if not isinstance(evidence_value, str) or not Path(evidence_value).is_absolute():
        raise ValueError("The receipt has no absolute evidence directory.")
    evidence_path = Path(evidence_value)
    if evidence_path.is_symlink():
        raise ValueError("The task evidence directory must not be a symlink.")
    evidence = evidence_path.resolve(strict=True)
    if evidence == private or not _contained(evidence, private):
        raise ValueError("The task evidence directory is outside private temporary storage.")

    tasks = report.get("tasks")
    if not isinstance(tasks, list) or any(not isinstance(task, dict) for task in tasks):
        raise ValueError("The receipt has no task list.")
    failed = [task for task in tasks if task.get("status") == "failed"]

    if destination.exists() or destination.is_symlink():
        raise ValueError("The failed-log artifact directory already exists.")

    manifest_tasks: list[dict[str, Any]] = []
    staged_files: list[tuple[str, bytes]] = []
    seen_task_ids: set[str] = set()
    for task in failed:
        task_id = task.get("taskId")
        log_name = task.get("logFile")
        expected_digest = task.get("logSha256")
        if not isinstance(task_id, str) or re.fullmatch(
            r"[A-Za-z0-9_.-]{1,100}", task_id
        ) is None:
            raise ValueError("A failed task has an invalid task id.")
        if task_id in seen_task_ids:
            raise ValueError(f"Failed task id {task_id} is duplicated.")
        seen_task_ids.add(task_id)
        if (
            not isinstance(log_name, str)
            or Path(log_name).name != log_name
            or "\\" in log_name
            or not log_name.endswith(".log")
        ):
            raise ValueError(f"Failed task {task_id} has an invalid log filename.")
        if (
            not isinstance(expected_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None
        ):
            raise ValueError(f"Failed task {task_id} has an invalid log digest.")

        source = evidence / log_name
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"Failed task {task_id} has no regular task log.")
        resolved_source = source.resolve(strict=True)
        if not _contained(resolved_source, evidence):
            raise ValueError(f"Failed task {task_id} log escapes the evidence directory.")
        content = resolved_source.read_bytes()
        actual_digest = hashlib.sha256(content).hexdigest()
        if actual_digest != expected_digest:
            raise ValueError(f"Failed task {task_id} log does not match its receipt digest.")

        artifact_name = f"{task_id}.log"
        staged_files.append((artifact_name, content))
        manifest_tasks.append(
            {
                "taskId": task_id,
                "exitCode": task.get("exitCode"),
                "logFile": artifact_name,
                "logSha256": actual_digest,
            }
        )

    destination.mkdir(mode=0o700)
    for artifact_name, content in staged_files:
        with (destination / artifact_name).open("xb") as artifact_log:
            artifact_log.write(content)
    manifest = {
        "schemaVersion": 1,
        "repository": report.get("repository"),
        "failedTaskCount": len(manifest_tasks),
        "tasks": manifest_tasks,
    }
    with (destination / "manifest.json").open(
        "x", encoding="utf-8"
    ) as artifact_manifest:
        artifact_manifest.write(json.dumps(manifest, indent=2) + "\n")
    return manifest_tasks


def main() -> int:
    try:
        private_root = Path(os.environ["PRIVATE_RUNNER_TEMP"])
        receipt_path = Path(os.environ["VALIDATION_RECEIPT_EXPORT"])
        destination = private_root / "romarr-validation" / "failed-task-logs"
        manifest = stage_failed_pytest_logs(receipt_path, private_root, destination)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"Unable to stage failed pytest task logs: {error}", file=sys.stderr)
        return 1

    print(f"Staged {len(manifest)} receipt-verified failed pytest task log(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
