from romarr.dat import parse_dat
from romarr.dat_catalog import (
    dat_catalog_game,
    dat_catalog_page,
    dat_catalog_platforms,
    platform_for_dat_name,
)


def test_dat_platform_name_uses_the_longest_declared_system_match():
    assert platform_for_dat_name(
        "Nintendo - Game Boy Advance (2024-01-01)"
    ).slug == "gba"
    assert platform_for_dat_name("Nintendo") is not None


def test_dat_catalog_collapses_regions_and_uses_stable_provider_keys():
    dat = parse_dat(
        '''<datafile><header><name>Nintendo - Super Nintendo Entertainment System</name><version>2025</version></header>
        <game name="Chrono Trigger (Europe)"><rom name="ct-eu.sfc"/></game>
        <game name="Chrono Trigger (USA)"><rom name="ct-us.sfc"/></game>
        <game name="Super Metroid (USA)"><rom name="sm.sfc"/></game>
        </datafile>'''
    )

    page, next_offset = dat_catalog_page([dat], limit=1)
    assert len(page) == 1
    assert next_offset == 1
    assert page[0]["catalogProvider"] == "dat"
    assert page[0]["catalogId"].startswith("dat-")
    assert page[0]["title"] == "Chrono Trigger"
    assert page[0]["dat"]["variants"] == 2
    assert page[0]["platformOptions"][0]["key"] == "snes"

    by_key = dat_catalog_game([dat], page[0]["catalogId"])
    assert by_key == page[0]

    changed_version = parse_dat(
        '''<datafile><header><name>Nintendo - Super Nintendo Entertainment System</name><version>2026</version></header>
        <game name="Chrono Trigger (Japan)"><rom name="ct-jp.sfc"/></game>
        <game name="Chrono Trigger (USA)"><rom name="ct-us.sfc"/></game>
        <game name="Super Metroid (USA)"><rom name="sm.sfc"/></game>
        </datafile>'''
    )
    refreshed, _ = dat_catalog_page([changed_version], query="Chrono Trigger")
    assert refreshed[0]["catalogId"] == page[0]["catalogId"]


def test_dat_catalog_search_platform_filter_and_unmatched_diagnostics():
    snes = parse_dat(
        '''<datafile><header><name>Nintendo - Super Nintendo Entertainment System</name></header>
        <game name="Chrono Trigger (USA)"/></datafile>'''
    )
    unknown = parse_dat(
        '''<datafile><header><name>Unknown Home Computer</name></header>
        <game name="Unknown Game"/></datafile>'''
    )
    rows, next_offset = dat_catalog_page(
        [snes, unknown], platform_slugs=["snes"], query="chrono"
    )
    assert [row["title"] for row in rows] == ["Chrono Trigger"]
    assert next_offset is None
    status = dat_catalog_platforms([snes, unknown])
    assert status["results"] == [
        {"slug": "snes", "name": "Super Nintendo", "gameCount": 1}
    ]
    assert status["unmatchedDatNames"] == ["Unknown Home Computer"]


def test_dat_catalog_rejects_bad_cursors_and_platform_slugs():
    dat = parse_dat(
        '''<datafile><header><name>Nintendo - Super Nintendo Entertainment System</name></header>
        <game name="Chrono Trigger (USA)"/></datafile>'''
    )
    import pytest

    with pytest.raises(ValueError):
        dat_catalog_page([dat], offset=10001)
    with pytest.raises(ValueError):
        dat_catalog_page([dat], platform_slugs=["../library"])
