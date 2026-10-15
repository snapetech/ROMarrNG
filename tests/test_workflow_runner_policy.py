import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
HOSTED_RUNNERS = {"ubuntu-latest", "macos-latest", "windows-latest"}
TRUSTED_MAIN_CONDITION = (
    "((github.event_name == 'push' && github.ref == 'refs/heads/main') "
    "|| (github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'))"
)
TRUSTED_MAIN_RUNNER_JSON = '{"group":"trusted-main","labels":["self-hosted","Linux","X64","host"]}'
TRUSTED_MAIN_RUNNER = (
    "$" + "{{ (" + TRUSTED_MAIN_CONDITION
    + " && vars.TRUSTED_MAIN_RUNNERS_ENABLED == 'true' "
    + "&& fromJSON('" + TRUSTED_MAIN_RUNNER_JSON + "')) || 'ubuntu-latest' }}"
)


def _runner_policy_violations(workflow_dir: Path) -> list[str]:
    workflow_files = sorted(
        path
        for suffix in ("*.yml", "*.yaml")
        for path in workflow_dir.glob(suffix)
        if path.is_file()
    )
    if not workflow_files:
        return ["workflow files must be present"]

    violations: list[str] = []
    runner_count = 0
    for workflow in workflow_files:
        document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            violations.append(f"{workflow.name}: workflow must be a YAML mapping")
            continue

        jobs = document.get("jobs")
        if not isinstance(jobs, dict):
            violations.append(f"{workflow.name}: jobs must be a YAML mapping")
            continue

        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                violations.append(
                    f"{workflow.name}/{job_name}: job must be a YAML mapping"
                )
                continue
            if "uses" in job and "runs-on" not in job:
                violations.append(
                    f"{workflow.name}/{job_name}: reusable workflow runner is not "
                    "visible in this file"
                )
                continue

            runner = job.get("runs-on")
            runner_count += 1
            location = f"{workflow.name}/{job_name}"
            if (
                workflow.name == "docker.yml"
                and job_name == "test"
                and runner == TRUSTED_MAIN_RUNNER
            ):
                continue
            if runner == "ubuntu-latest":
                continue
            if runner == "${{ matrix.os }}":
                strategy = job.get("strategy")
                matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
                matrix_os = matrix.get("os") if isinstance(matrix, dict) else None
                if (
                    isinstance(matrix_os, list)
                    and matrix_os
                    and all(
                        isinstance(label, str) and label in HOSTED_RUNNERS
                        for label in matrix_os
                    )
                    and "include" not in matrix
                ):
                    continue
                violations.append(
                    f"{location}: matrix.os must contain only hosted runner labels"
                )
                continue

            violations.append(
                f"{location}: unsupported runner assignment {runner!r}; "
                "public workflows must use hosted runners except for the exact trusted-main job"
            )

    if runner_count == 0:
        violations.append("no checked-in workflow runner assignments were found")
    return violations


class WorkflowRunnerPolicyTests(unittest.TestCase):
    def test_public_workflows_use_hosted_runners_except_trusted_main_job(self) -> None:
        self.assertEqual(
            _runner_policy_violations(WORKFLOW_DIR),
            [],
            "only docker.yml/test on trusted main may select the organization pool",
        )

    def test_quoted_runner_key_in_yaml_file_is_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workflow_dir = Path(temporary_directory)
            (workflow_dir / "quoted-runner.yaml").write_text(
                "name: runner policy regression\n"
                "on: push\n"
                "jobs:\n"
                "  test:\n"
                "    \"runs-on\": self-hosted\n"
                "    steps: []\n",
                encoding="utf-8",
            )

            violations = _runner_policy_violations(workflow_dir)

        self.assertEqual(len(violations), 1)
        self.assertIn("unsupported runner assignment 'self-hosted'", violations[0])

    def test_matrix_include_cannot_add_a_persistent_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workflow_dir = Path(temporary_directory)
            (workflow_dir / "matrix.yml").write_text(
                "jobs:\n"
                "  test:\n"
                "    runs-on: ${{ matrix.os }}\n"
                "    strategy:\n"
                "      matrix:\n"
                "        os: [ubuntu-latest]\n"
                "        include:\n"
                "          - os: self-hosted\n",
                encoding="utf-8",
            )

            violations = _runner_policy_violations(workflow_dir)

        self.assertEqual(len(violations), 1)
        self.assertIn("matrix.os must contain only hosted runner labels", violations[0])


    def test_pool_python_runtime_is_private_and_distro_independent(self) -> None:
        workflow = yaml.safe_load(
            (WORKFLOW_DIR / "docker.yml").read_text(encoding="utf-8")
        )
        steps = workflow["jobs"]["test"]["steps"]
        hosted_python = next(
            step
            for step in steps
            if step.get("name") == "Set up Python 3.13 on GitHub-hosted runners"
        )
        self.assertEqual(hosted_python["if"], "runner.environment == 'github-hosted'")
        self.assertEqual(
            hosted_python["uses"],
            "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
        )

        setup_uv = next(
            step
            for step in steps
            if step.get("name") == "Install uv for the self-hosted Python runtime"
        )
        self.assertEqual(setup_uv["if"], "runner.environment == 'self-hosted'")
        self.assertEqual(
            setup_uv["uses"],
            "astral-sh/setup-uv@1c37ad07a6a961277cf70c0d37d6f313000f5884",
        )
        self.assertEqual(setup_uv["with"]["version"], "0.13.0")
        self.assertIs(setup_uv["with"]["enable-cache"], False)

        private_python = next(
            step
            for step in steps
            if step.get("name") == "Install Python 3.13 in private runner storage"
        )
        self.assertEqual(private_python["if"], "runner.environment == 'self-hosted'")
        self.assertEqual(
            private_python["env"]["UV_PYTHON_INSTALL_DIR"],
            "${{ steps.private-runner-temp.outputs.path }}/python",
        )
        self.assertEqual(
            private_python["env"]["UV_CACHE_DIR"],
            "${{ steps.private-runner-temp.outputs.path }}/uv-cache",
        )
        self.assertIn("uv python install 3.13", private_python["run"])
        self.assertIn("uv python find 3.13", private_python["run"])
        self.assertIn(
            '[[ "$python_bin" == "$UV_PYTHON_INSTALL_DIR/"* && -x "$python_bin" ]]',
            private_python["run"],
        )
        self.assertIn('>> "$GITHUB_PATH"', private_python["run"])


if __name__ == "__main__":
    unittest.main()
