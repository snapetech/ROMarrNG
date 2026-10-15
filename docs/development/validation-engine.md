# Validation engine

ROMarrNG keeps pytest as its test runner and uses a small Python orchestration
layer to record which source and test inventory produced each result.

## Local use

```sh
node /path/to/trusted-test-launcher.mjs "$PWD" -- python3.13 -m pytest tests/ -q
```

The local command runs an already-configured Python 3.13 environment inside the
trusted, offline Linux bubblewrap launcher. Have pytest, test-only PyYAML, and
`requirements.txt` dependencies installed in that environment before running
it; the launcher does not install candidate dependencies or inherit
package-index credentials.
When evaluating an unreviewed branch, copy `trusted-test-launcher.mjs` and
`trusted-test-sandbox-policy.mjs` from the same reviewed revision to a location
outside the checkout, keeping them together. Its default command is the same
pytest invocation:

```sh
node /path/to/trusted-test-launcher.mjs "$PWD"
```

The launcher has no network access. It copies only Git-index paths into a
temporary workspace, so untracked and ignored local files never enter the
snapshot. Dotted and extensionless credentials, private/API keys,
access/refresh-token names, client-secret names, and credential material with
source-like extensions are excluded. Suffixed dotenv credentials such as
tokens.env.local are excluded, while tokens.env.example remains available.
Source files under credential-named folders remain available unless their own
names identify credential material.
Stage new candidate files before launching it. The sandbox hides the
canonical checkout parent and common host configuration and data roots,
including `/etc`, `/home`, `/run`, `/srv`, and `/tmp`. Standard program roots
such as `/opt` and `/usr/local` stay available so the preconfigured interpreter
and its dependencies can run. When a checkout is nested beneath a recognized
workspace directory, the sandbox masks that workspace root and its sibling
checkouts. Run planning for an unreviewed candidate through it too, because
planning imports candidate validation configuration.
GitHub Actions remains responsible for receipt-backed validation.

In CI, `--plan` discovers files and required commands without installing
packages or running pytest. Pull requests, version-tag pushes, and manual runs
outside main use GitHub-hosted runners. Trusted pushes to main and manual runs
targeting main use the shared organization runner pool only when the repository
variable `TRUSTED_MAIN_RUNNERS_ENABLED` is `true`; otherwise the Linux pytest job
uses `ubuntu-latest`. The organization runner group is restricted server-side to
snapetech-org/ROMarrNG/.github/workflows/docker.yml@refs/heads/main. That policy
prevents pull-request versions of this public workflow from selecting the
persistent pool, while the workflow expression keeps PRs, tags, and non-main
manual runs hosted. Pushes to other branches do
not trigger this workflow. The Linux validation job uses `setup-python` with
Python 3.13 on GitHub-hosted runners. On the trusted Arch Linux pool, it installs a pinned uv
CLI and uses it to install managed Python 3.13 beneath the job's private
`RUNNER_TEMP` directory, then adds that interpreter to the job path. This keeps
the test runtime independent of the runner distribution and avoids global
installation paths. The job uses the validation engine to install repository
requirements, pytest, and test-only PyYAML in a task environment before running
the native suite. The engine divides discovered test files into four
disjoint inventory shards and runs at most two shards at once after dependency
installation completes. Each shard has its own environment and log, and
disables pytest's shared cache plugin. The test tasks use `pytest.ini` as
configured, including its default `not network` marker, so tests that reach the
public internet remain deselected. The engine counts passed, skipped, failed,
and deselected cases from every pytest summary, records each shard's file
inventory in one receipt, and does not call an empty run successful. Image
validation reconciles every shard against that same source receipt before
building.

Pull-request image jobs smoke-test the Alpine image and build the browser
image for its supported platforms, all with read-only repository permissions.
Separate publishing jobs receive registry
write and OIDC attestation permissions only for pushes to `main`, version
tags, or manual runs targeting `main`. The release job runs only for version
tags after both published images succeed.

The engine writes a compact task summary to stderr at task start and completion,
with a once-per-minute heartbeat during long tasks. Counts cover completed
tasks; all active tasks and their elapsed times are shown separately. GitHub publishes
workflow step summaries after the step finishes, so live progress appears in
the step log.

Each run uses a new private temporary directory for its receipt and hashed
per-task logs. The candidate fingerprint includes the Git commit/tree and diff,
untracked files, the discovered `tests/test_*.py` file hashes, and the test
workflow, pytest configuration, and requirements input digests. A change during
execution blocks the result. No result cache is reused. The engine drains child
output in a background reader, retains only the bounded diagnostic tail in
memory, and caps the private log at 16 MiB with an explicit truncation marker.
Sandbox mounts are pinned through inherited file descriptors before the
launcher masks host paths.

Runtime probes and child commands receive only an inherited allowlist for
executable paths, platform process variables, locale, and timezone, plus child
tasks' declared settings. Proxy, private-index, and custom CA settings are
passed only to the dependency-install task; pytest never receives them. Each
task uses run-owned home, temporary, XDG, and pip cache directories, and Python
user-site packages are disabled. Test children receive `CI=true`; ambient
credentials, Python path injection, and user configuration paths are not
inherited. On Linux the runner also disables procfs access to its own process
environment while a task child is running. This requires a non-root runner
without `CAP_SYS_PTRACE`; the engine refuses to start a task when that boundary
cannot be enforced or the runner's original dumpability state cannot be
restored.

The CI job exports a short-lived receipt with the absolute path to its private
evidence directory and any receipt-verified failed shard logs from the Linux x64
pytest runner. Successful shard logs remain in private runner storage. The image
job checks the receipt's run ID, attempt, commit,
runner identity, case count, and inventory digest against the image job's own
checkout before building an image.
This confirms the artifact came from the current workflow attempt and the same
source snapshot; it does not replace the local test evidence.

The `install-test-dependencies` task runs only in hosted CI. Running the engine's
`--tests-only` selection locally is intentionally refused because it includes
that package-install task; use the trusted launcher with the preconfigured
Python environment instead. The workflow currently installs `requirements.txt`,
pytest, and test-only PyYAML without a Python dependency lockfile. The engine
binds those manifests and the Python 3.13 runtime, but dependency versions are
not yet reproducible from a lockfile.
