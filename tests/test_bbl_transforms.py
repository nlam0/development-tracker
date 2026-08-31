"""Pure tests for pipeline/transforms/bbl.py -- no network or DB.

Covers all four source input shapes named in IMPLEMENTATION_PLAN.md Risk R3,
plus the borough/block/lot round trip that pipeline/sources/pluto.py relies
on to keep parcels.bbl and parcels.(borough, block, lot) from diverging.
"""

import pytest

from pipeline.transforms.bbl import (
    normalize_bbl,
    normalize_bbl_acris,
    normalize_bbl_dob_legacy,
    normalize_bbl_dob_now,
    normalize_bbl_pluto,
    parse_bbl,
)


def test_normalize_bbl_pluto_strips_float_formatting():
    assert normalize_bbl_pluto("1002000001.00000000") == "1002000001"


def test_normalize_bbl_dob_now_handles_int_and_float():
    assert normalize_bbl_dob_now(1012730012) == "1012730012"
    assert normalize_bbl_dob_now(1012730012.0) == "1012730012"


def test_normalize_bbl_dob_legacy_zero_pads_block_and_lot():
    assert normalize_bbl_dob_legacy("MANHATTAN", "1413", "1") == "1014130001"
    assert normalize_bbl_dob_legacy("manhattan", "01413", "00001") == "1014130001"


def test_normalize_bbl_acris_zero_pads_block_and_lot():
    assert normalize_bbl_acris("1", "200", "6") == "1002000006"


def test_normalize_bbl_rejects_unrecognized_borough_name():
    with pytest.raises(ValueError):
        normalize_bbl("NARNIA", "1", "1")


@pytest.mark.parametrize(
    "bbl,expected",
    [
        ("1002000006", (1, 200, 6)),
        ("4087860042", (4, 8786, 42)),
    ],
)
def test_parse_bbl_round_trips_with_normalize_bbl(bbl, expected):
    assert parse_bbl(bbl) == expected


def test_parse_bbl_rejects_wrong_length():
    with pytest.raises(ValueError):
        parse_bbl("123")


def test_parse_bbl_rejects_non_digit():
    with pytest.raises(ValueError):
        parse_bbl("1abc000006")
