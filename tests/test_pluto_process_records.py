"""Pure tests for pipeline.sources.pluto.process_records -- no network or DB.

These cover the validate/normalize/filter stages, and specifically the
reject paths: PRD §14 requires malformed records be logged rather than
dropped, and a single bad value must not fail an entire 42,000-record run.
"""

from pipeline.sources.pluto import process_records

AREAS = {"1002000001": "Chinatown", "1002000002": "Two Bridges"}


def _raw(bbl, **over):
    row = {"bbl": bbl, "address": "1 TEST ST", "lotarea": "100", "version": "26v2"}
    row.update(over)
    return row


def test_keeps_only_study_area_bbls():
    rows, rejected, received = process_records(
        [_raw("1002000001.00000000"), _raw("1099990099.00000000")], AREAS
    )
    assert set(rows) == {"1002000001"}
    assert received == 2
    assert rejected == []  # outside the study area is a filter, not a rejection


def test_missing_bbl_is_rejected_not_dropped():
    rows, rejected, _ = process_records([_raw(None)], AREAS)
    assert rows == {}
    assert [r[0] for r in rejected] == ["missing bbl"]


def test_unparseable_bbl_is_rejected():
    rows, rejected, _ = process_records([_raw("not-a-bbl")], AREAS)
    assert rows == {}
    assert [r[0] for r in rejected] == ["unparseable bbl"]


def test_unparseable_field_rejects_only_that_record():
    """One bad numeric must not take the whole run down with it."""
    rows, rejected, received = process_records(
        [
            _raw("1002000001.00000000", lotarea="N/A"),
            _raw("1002000002.00000000"),
        ],
        AREAS,
    )
    assert received == 2
    assert set(rows) == {"1002000002"}, "the good record must still load"
    assert len(rejected) == 1
    assert rejected[0][0].startswith("unparseable field")


def test_duplicate_bbl_collapses_to_one_row_per_conflict_key():
    """The batched upsert raises CardinalityViolation on a repeated key."""
    rows, _, received = process_records(
        [
            _raw("1002000001.00000000", address="OLD"),
            _raw("1002000001.00000000", address="NEW"),
        ],
        AREAS,
    )
    assert received == 2
    assert len(rows) == 1
    assert rows["1002000001"]["address"] == "NEW"


def test_year_built_zero_becomes_null():
    rows, _, _ = process_records([_raw("1002000001.00000000", yearbuilt="0")], AREAS)
    assert rows["1002000001"]["year_built"] is None
