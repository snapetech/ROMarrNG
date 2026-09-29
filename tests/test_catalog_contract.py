import pytest

from romarr.app import _parse_igdb_platform_id


def test_catalog_platform_id_is_optional_and_accepts_the_contract_limit():
    assert _parse_igdb_platform_id(None) is None
    assert _parse_igdb_platform_id([]) is None
    assert _parse_igdb_platform_id(["48"]) == 48
    assert _parse_igdb_platform_id(["1000000"]) == 1_000_000


@pytest.mark.parametrize("values", [
    ["0"],
    ["1000001"],
    ["48", "49"],
    ["48x"],
    ["-48"],
])
def test_catalog_platform_id_rejects_malformed_or_out_of_range_values(values):
    with pytest.raises(ValueError, match="invalid IGDB platform ID"):
        _parse_igdb_platform_id(values)
