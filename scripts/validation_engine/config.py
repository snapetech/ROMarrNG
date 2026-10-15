"""ROMarrNG's native pytest validation task and its input boundaries."""

REPOSITORY = "romarrng"
INPUTS = (
    ".gitignore",
    "pytest.ini",
    "requirements.txt",
    ".github/workflows/docker.yml",
    "release-notes/README.md",
    "release-notes/20261012-validation-environment-isolation.md",
    "release-notes/20261012-trusted-test-sandbox.md",
    "release-notes/20261012-validation-security-review.md",
    "release-notes/20261012-validation-sandbox-hardening.md",
    "docs/development/validation-engine.md",
    "scripts/validation_engine/__init__.py",
    "scripts/validation_engine/config.py",
    "scripts/validation_engine/engine.py",
    "scripts/validation_engine/run_pytest_shard.py",
    "scripts/validation_engine/trusted_sandbox.py",
    "scripts/validation_engine/trusted-test-launcher.mjs",
    "scripts/validation_engine/trusted-test-launcher.contract.mjs",
    "scripts/validation_engine/reconcile.py",
    "tests/test_validation_engine.py",
    "release-notes/20261011-validation-engine.md",
    "release-notes/20261013-bounded-validation-task-pool.md",
)
MAX_CONCURRENT_TASKS = 2
PYTEST_SHARDS = (
    {"id": "hnrs", "letters": "hnrs"},
    {"id": "abcdgo", "letters": "abcdgo"},
    {"id": "eimqtw", "letters": "eimqtw"},
    {"id": "flpuv", "letters": "flpuv"},
)
INVENTORY = tuple(
    {
        "id": f"pytest-shard-{shard['id']}",
        "glob": f"tests/test_[{shard['letters']}]*.py",
        "framework": "pytest",
        "owner": f"pytest-shard-{shard['id']}",
    }
    for shard in PYTEST_SHARDS
)
TEST_TASKS = tuple(
    {
        "id": f"pytest-shard-{shard['id']}",
        "name": f"Offline pytest shard ({shard['letters']})",
        "stage": "repository",
        "kind": "test",
        "concurrency_group": f"pytest-shard-{shard['id']}",
        "command": [
            "{PYTHON}", "scripts/validation_engine/run_pytest_shard.py", shard["letters"],
        ],
        "parser": "pytest",
        "minimum_cases": 1,
        "inventory_lanes": [f"pytest-shard-{shard['id']}"],
        "depends_on": ["install-test-dependencies"],
        "timeout_seconds": 1800,
    }
    for shard in PYTEST_SHARDS
)
TASKS = (
    {
        "id": "create-test-environment",
        "name": "Create disposable Python test environment",
        "stage": "prepare",
        "concurrency_group": "python-environment",
        "kind": "setup",
        "command": ["python3.13", "-m", "venv", "{VENV}"],
        "timeout_seconds": 180,
    },
    {
        "id": "install-test-dependencies",
        "name": "Install pytest dependencies into disposable environment",
        "stage": "prepare",
        "concurrency_group": "python-environment",
        "kind": "setup",
        "command": [
            "{PYTHON}", "-m", "pip", "install", "--disable-pip-version-check",
            "--no-cache-dir", "-r", "requirements.txt", "pytest", "PyYAML",
        ],
        "pass_env": [
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
            "http_proxy", "https_proxy", "all_proxy", "no_proxy",
            "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_TRUSTED_HOST",
            "PIP_CERT", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
            "SSL_CERT_FILE", "SSL_CERT_DIR",
        ],
        "depends_on": ["create-test-environment"],
        "timeout_seconds": 1200,
    },
    *TEST_TASKS,
)
