"""Pure tests for pipeline.sources.dob_now -- no network or DB.

external_id and process_records cover the validate/normalize/categorize
stages exactly like tests/test_pluto_process_records.py does for M3:
membership (study-area placement) and job_types (category lookup) are
passed in already-resolved, since those two stages are the DB/network-
dependent ones this file deliberately doesn't exercise.
"""

from pipeline.sources.dob_now import CATEGORY_MAP, external_id, process_records

BBL_MATCH = ("1002000001", "Chinatown", "bbl")
SPATIAL_MATCH = (None, "Two Bridges", "spatial")


def _raw(**over):
    row = {
        "job_filing_number": "M01248246-I1",
        "work_permit": "M01248246-I1-EW-SP",
        "sequence_number": "1",
        "work_type": "Sprinklers",
        "tracking_number": "912522473",
        "filing_reason": "Initial Permit",
        "house_no": "12",
        "street_name": "EAST 52 STREET",
        "permit_status": "Signed-off",
        "job_description": "test description",
        "estimated_job_costs": "20000",
        "owner_name": "SAMUEL RAMIREZ",
        "approved_date": "2025-08-14T00:00:00.000",
        "issued_date": "2025-09-19T00:00:00.000",
        "expired_date": "2026-06-06T00:00:00.000",
        "bin": "1035477",
        "bbl": "1002000001",
        "latitude": "40.759481",
        "longitude": "-73.975581",
    }
    row.update(over)
    return row


# -- external_id -------------------------------------------------------


def test_external_id_uses_composite_key_when_all_components_present():
    eid = external_id(_raw())
    assert eid == "M01248246-I1|M01248246-I1-EW-SP|1|Sprinklers|912522473"


def test_external_id_falls_back_to_hash_on_sentinel_filing():
    raw = _raw(job_filing_number="Permit is no", work_permit="Permit is not yet issued")
    assert external_id(raw).startswith("hash:")


def test_external_id_falls_back_to_hash_on_missing_sequence_number():
    row = _raw()
    del row["sequence_number"]
    assert external_id(row).startswith("hash:")


def test_external_id_falls_back_to_hash_on_missing_tracking_number():
    row = _raw()
    del row["tracking_number"]
    assert external_id(row).startswith("hash:")


def test_external_id_is_stable_for_identical_input():
    assert external_id(_raw()) == external_id(_raw())


# -- process_records ----------------------------------------------------


def test_only_records_with_resolved_membership_are_kept():
    raw = _raw()
    eid = external_id(raw)
    records = {eid: raw, "other": _raw(tracking_number="999")}
    membership = {eid: BBL_MATCH}
    rows, rejected, received = process_records(records, membership, {})
    assert received == 2
    assert set(rows) == {eid}
    assert rejected == []  # not in the study area is a filter, not a rejection


def test_bbl_match_keeps_bbl_and_records_match_type():
    raw = _raw()
    eid = external_id(raw)
    rows, _, _ = process_records({eid: raw}, {eid: BBL_MATCH}, {})
    row = rows[eid]
    assert row["bbl"] == "1002000001"
    assert row["neighborhood"] == "Chinatown"
    assert row["study_area_match"] == "bbl"


def test_spatial_match_nulls_bbl_even_when_source_bbl_present():
    """D7(b): a spatially-matched permit's own bbl has no parcels row (it
    wasn't in the allowlist, or it wouldn't be a spatial match), so the FK
    can't hold it."""
    raw = _raw()
    eid = external_id(raw)
    rows, _, _ = process_records({eid: raw}, {eid: SPATIAL_MATCH}, {})
    row = rows[eid]
    assert row["bbl"] is None
    assert row["neighborhood"] == "Two Bridges"
    assert row["study_area_match"] == "spatial"


def test_category_maps_from_job_type_via_job_filing_number():
    raw = _raw(job_filing_number="B00319790-I1")
    eid = external_id(raw)
    job_types = {"B00319790-I1": "New Building"}
    rows, _, _ = process_records({eid: raw}, {eid: BBL_MATCH}, job_types)
    assert rows[eid]["category"] == "new_building"


def test_category_defaults_to_other_when_job_type_unresolved():
    raw = _raw()
    eid = external_id(raw)
    rows, _, _ = process_records({eid: raw}, {eid: BBL_MATCH}, {})
    assert rows[eid]["category"] == "other"


def test_category_map_covers_all_six_observed_job_types():
    assert set(CATEGORY_MAP) == {
        "New Building",
        "ALT-CO - New Building with Existing Elements to Remain",
        "Full Demolition",
        "Alteration",
        "Alteration CO",
        "No Work",
    }


def test_event_date_prefers_issued_date_falling_back_to_approved_date():
    raw = _raw(issued_date=None)
    eid = external_id(raw)
    rows, _, _ = process_records({eid: raw}, {eid: BBL_MATCH}, {})
    assert str(rows[eid]["event_date"]) == "2025-08-14"


def test_missing_both_dates_is_rejected_not_dropped():
    raw = _raw(approved_date=None, issued_date=None)
    eid = external_id(raw)
    rows, rejected, _ = process_records({eid: raw}, {eid: BBL_MATCH}, {})
    assert rows == {}
    assert len(rejected) == 1
    assert "missing event date" in rejected[0][0]


def test_empty_cost_becomes_null_not_a_reject():
    raw = _raw(estimated_job_costs="")
    eid = external_id(raw)
    rows, rejected, _ = process_records({eid: raw}, {eid: BBL_MATCH}, {})
    assert rejected == []
    assert rows[eid]["estimated_cost"] is None


def test_unparseable_cost_rejects_only_that_record():
    good = _raw()
    bad = _raw(tracking_number="000", estimated_job_costs="N/A")
    good_id, bad_id = external_id(good), external_id(bad)
    records = {good_id: good, bad_id: bad}
    membership = {good_id: BBL_MATCH, bad_id: BBL_MATCH}
    rows, rejected, received = process_records(records, membership, {})
    assert received == 2
    assert set(rows) == {good_id}
    assert len(rejected) == 1
    assert rejected[0][0].startswith("unparseable field")


def test_address_built_from_house_no_and_street_name():
    raw = _raw()
    eid = external_id(raw)
    rows, _, _ = process_records({eid: raw}, {eid: BBL_MATCH}, {})
    assert rows[eid]["address"] == "12 EAST 52 STREET"


def test_permit_type_is_always_null_for_dob_now():
    """rbx6-tga4 has no permit_type field -- see module docstring."""
    raw = _raw()
    eid = external_id(raw)
    rows, _, _ = process_records({eid: raw}, {eid: BBL_MATCH}, {})
    assert rows[eid]["permit_type"] is None
