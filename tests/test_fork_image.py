"""The fork must publish and install its own container image."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_docker_workflow_publishes_to_current_repository() -> None:
    workflow = (ROOT / ".github/workflows/docker.yml").read_text()
    assert 'name=ghcr.io/${GITHUB_REPOSITORY,,}' in workflow
    assert "images: ${{ steps.image.outputs.name }}" in workflow
    assert "ghcr.io/blizzhacker/romarr" not in workflow


def test_install_surfaces_use_romarrng_image() -> None:
    for file in (
        "docker-compose.yml",
        "README.md",
        "docs/INSTALL.md",
        "homeassistant/romarr/config.yaml",
    ):
        content = (ROOT / file).read_text()
        assert "ghcr.io/snapetech/romarrng" in content, file
        assert "ghcr.io/blizzhacker/romarr:latest" not in content, file
