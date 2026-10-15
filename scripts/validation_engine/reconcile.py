"""Verify the pytest node receipt belongs to the current ROMarrNG workflow."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from . import config
from .engine import ROOT, ValidationError, capture_candidate, inventory_files

NODE_ID = "romarrng-pytest-linux"
TASK_IDS = tuple(f"pytest-shard-{shard['id']}" for shard in config.PYTEST_SHARDS)


def reconcile_receipts(receipts: list[dict[str, Any]], run_id: str, run_attempt: str, sha: str, current_candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    if not run_id or not run_attempt or not re.fullmatch(r"[a-f0-9]{40}", sha or ""):
        raise ValidationError("A GitHub run ID, attempt, and full source commit are required.")
    if len(receipts) != 1:
        raise ValidationError("Expected exactly one current ROMarrNG pytest node receipt.")
    receipt = receipts[0]
    context = receipt.get("executionContext") or {}
    github = context.get("github") or {}
    tasks = receipt.get("tasks", [])
    tasks_by_id = {item.get("taskId"): item for item in tasks}
    if receipt.get("schemaVersion") != 2 or receipt.get("repository") != "romarrng":
        raise ValidationError("Receipt schema or repository does not match ROMarrNG.")
    if receipt.get("maxConcurrentTasks") != config.MAX_CONCURRENT_TASKS:
        raise ValidationError("Receipt does not attest the configured bounded task pool.")
    if receipt.get("status") != "passed" or len(tasks_by_id) != len(tasks) or any(
        task_id not in tasks_by_id or tasks_by_id[task_id].get("status") != "passed"
        for task_id in TASK_IDS
    ):
        raise ValidationError("Pytest node did not record passing receipts for every test shard.")
    shard_tasks = [tasks_by_id[task_id] for task_id in TASK_IDS]
    cases_by_task = [task.get("activeCases") for task in shard_tasks]
    if any(not isinstance(cases, int) or cases < 1 for cases in cases_by_task):
        raise ValidationError("Pytest node has a shard with no positive passing case count.")
    cases = sum(cases_by_task)
    totals = receipt.get("totals", {})
    if totals.get("activeCases") != cases:
        raise ValidationError("Pytest node aggregate case count does not match its shard receipts.")
    skipped = sum(task.get("skippedCases", 0) for task in shard_tasks)
    excluded = sum(task.get("excludedCases", 0) for task in shard_tasks)
    if totals.get("skippedCases", 0) != skipped or totals.get("excludedCases", 0) != excluded:
        raise ValidationError("Pytest node skip or exclusion totals do not match its shard receipts.")
    if receipt.get("selection") not in {"tests-only", "full"}:
        raise ValidationError("Receipt has an unexpected test selection.")
    if context.get("executor") != "github-actions" or context.get("nodeId") != NODE_ID:
        raise ValidationError("Receipt was not produced by the expected GitHub pytest node.")
    runner = context.get("runner") or {}
    if runner.get("os") != "Linux" or runner.get("architecture") != "X64":
        raise ValidationError("Receipt runner OS or architecture does not match the configured node.")
    if str(github.get("runId")) != str(run_id) or str(github.get("runAttempt")) != str(run_attempt):
        raise ValidationError("Receipt belongs to a different workflow run or attempt.")
    if github.get("sha") != sha or receipt.get("candidate", {}).get("commit") != sha:
        raise ValidationError("Receipt belongs to a different source commit.")
    candidate = receipt.get("candidate") or {}
    if not re.fullmatch(r"[a-f0-9]{40}", candidate.get("tree", "")) or not re.fullmatch(r"[a-f0-9]{64}", candidate.get("sourceSha256", "")) or not re.fullmatch(r"[a-f0-9]{64}", candidate.get("inventorySha256", "")):
        raise ValidationError("Receipt has an invalid source snapshot identity.")
    if current_candidate is not None:
        identity = ("commit", "tree", "sourceSha256", "inventorySha256", "inputDigests")
        if any(candidate.get(key) != current_candidate.get(key) for key in identity):
            raise ValidationError("Receipt and image job do not share the same source snapshot.")
    inventory_counts = receipt.get("inventoryCounts", {})
    inventory_digests = receipt.get("inventoryLaneDigests", {})
    discovered_files = 0
    for task_id, task in zip(TASK_IDS, shard_tasks, strict=True):
        count = inventory_counts.get(task_id)
        digest = inventory_digests.get(task_id)
        if not isinstance(count, int) or count < 1 or not re.fullmatch(r"[a-f0-9]{64}", digest or ""):
            raise ValidationError("Receipt is missing a pytest shard inventory.")
        inventory = {item.get("lane"): item for item in task.get("inventory", [])}
        if inventory.get(task_id, {}).get("discoveredFiles") != count or inventory.get(task_id, {}).get("inventorySha256") != digest:
            raise ValidationError("Test shard does not attest its discovered pytest inventory.")
        discovered_files += count
    return {
        "schemaVersion": 1,
        "repository": "romarrng",
        "runId": str(run_id),
        "runAttempt": str(run_attempt),
        "sha": sha,
        "status": "passed",
        "activeCases": cases,
        "skippedCases": skipped,
        "excludedCases": excluded,
        "inventoryFiles": discovered_files,
        "shards": [{
            "taskId": task_id,
            "activeCases": task.get("activeCases"),
            "skippedCases": task.get("skippedCases", 0),
            "excludedCases": task.get("excludedCases", 0),
        } for task_id, task in zip(TASK_IDS, shard_tasks, strict=True)],
        "nodeId": NODE_ID,
        "runner": runner,
        "completedAt": receipt.get("completedAt"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile a ROMarrNG CI test receipt")
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args(argv)
    receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    inventory, _ = inventory_files(ROOT, config.INVENTORY)
    current_candidate = capture_candidate(ROOT, config.INPUTS, inventory)
    summary = reconcile_receipts([receipt], args.run_id, args.run_attempt, args.sha, current_candidate)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as error:
        print(str(error))
        raise SystemExit(1)
