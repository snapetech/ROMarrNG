"""Alpine's musl runtime cannot install Playwright's manylinux wheels."""

import builtins

import pytest

from romarr import browser


def _block_playwright_import(monkeypatch):
    real_import = builtins.__import__

    def importing(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("no playwright")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importing)


def test_musl_install_points_to_the_romarrng_browser_image(monkeypatch):
    _block_playwright_import(monkeypatch)
    monkeypatch.setattr(browser, "_is_musl", lambda: True)

    with pytest.raises(browser.Unavailable) as error:
        browser._playwright()

    message = str(error.value)
    assert "musl" in message
    assert "ghcr.io/snapetech/romarrng:browser" in message
    assert "playwright run-server" in message


def test_glibc_install_keeps_the_local_playwright_instruction(monkeypatch):
    _block_playwright_import(monkeypatch)
    monkeypatch.setattr(browser, "_is_musl", lambda: False)

    with pytest.raises(browser.Unavailable) as error:
        browser._playwright()

    assert "musl" not in str(error.value)
    assert "pip install playwright" in str(error.value)
