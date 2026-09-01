"""Integration checks for the M3 PLUTO ingestion against the live database.

Skipped automatically when SUPABASE_DB_URL_DIRECT isn't configured (see
tests/conftest.py). These lock in the invariants pipeline/sources/pluto.py
depends on: parcels covers exactly the M1-resolved study-area BBL set (no
adapter-side leakage or under-fetching), every row has a usable point
geometry, and the PLUTO version stays pinned per decision D3.
"""

import pytest


def test_parcels_row_count_matches_resolved_study_area_bbls(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM parcels;")
        parcels_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM study_area_bbls;")
        bbls_count = cur.fetchone()[0]
    assert parcels_count == bbls_count
    assert parcels_count > 0


def test_parcels_neighborhood_counts_match_study_area_bbls(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT sa.name, count(*) FROM study_area_bbls b
            JOIN study_areas sa ON sa.id = b.study_area_id
            GROUP BY sa.name;
        """)
        expected = dict(cur.fetchall())
        cur.execute("SELECT neighborhood, count(*) FROM parcels GROUP BY neighborhood;")
        actual = dict(cur.fetchall())
    assert actual == expected


def test_null_geometry_occurs_only_on_block_resolved_parcels(db_conn):
    """Decision D6(b) admits lots PLUTO gives no centroid for, so a null geom
    is legitimate -- but only for those. Any centroid-resolved parcel missing
    a geometry means the point-in-polygon load itself dropped coordinates.
    """
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT b.resolution_method, count(*)
            FROM parcels p
            JOIN study_area_bbls b ON b.bbl = p.bbl
            WHERE p.geom IS NULL
            GROUP BY b.resolution_method;
        """)
        by_method = dict(cur.fetchall())
    assert by_method.get("centroid", 0) == 0, (
        "a centroid-resolved parcel lost its geometry during load"
    )


def test_block_resolved_parcels_are_loaded(db_conn):
    """The D6(b) lots are the point of the decision -- verify they arrived."""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM parcels p
            JOIN study_area_bbls b ON b.bbl = p.bbl
            WHERE b.resolution_method = 'block_membership';
        """)
        loaded = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM study_area_bbls WHERE resolution_method = 'block_membership';"
        )
        resolved = cur.fetchone()[0]
    assert loaded == resolved
    assert loaded > 0, "expected the centroid-less study-area lots to be admitted"


def test_parcels_bbl_is_canonical_ten_digit(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM parcels WHERE bbl !~ '^[0-9]{10}$';")
        assert cur.fetchone()[0] == 0


def test_parcels_pluto_version_is_pinned(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT pluto_version FROM parcels;")
        versions = {row[0] for row in cur.fetchall()}
    assert versions == {"26v2"}


def test_most_recent_completed_pluto_ingestion_run_succeeded(db_conn):
    """The last run that *finished* must have succeeded -- see the DOB NOW
    counterpart for why an in-flight run is excluded rather than counted as
    a failure."""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT status, records_rejected FROM ingestion_runs
            WHERE source = 'pluto' AND status <> 'running'
            ORDER BY started_at DESC LIMIT 1;
        """)
        row = cur.fetchone()
    assert row is not None, "no completed pluto ingestion_runs row found -- has M3 been run?"
    status, records_rejected = row
    assert status == "success"
    assert records_rejected == 0


@pytest.mark.writes_db
def test_upsert_tolerates_null_coordinates(db_conn):
    """Regression: under executemany the statement is prepared once, so an
    uncast null coordinate placeholder fails Postgres type inference. D6(b)
    lots have no centroid, making this a normal path rather than an edge case.

    Writes (and rolls back), so it needs write credentials -- CI runs
    read-only and deselects it. See pyproject's `writes_db` marker.
    """
    from pipeline.load import PARCEL_COLUMNS, upsert_parcels

    row = dict.fromkeys(PARCEL_COLUMNS)
    row.update(
        bbl="9999999999", borough=9, block=99999, lot=9999,
        latitude=None, longitude=None, pluto_version="test", neighborhood=None,
    )
    try:
        inserted, _ = upsert_parcels(db_conn, [row])
        assert inserted == 1
        with db_conn.cursor() as cur:
            cur.execute("SELECT geom FROM parcels WHERE bbl = '9999999999';")
            assert cur.fetchone()[0] is None
    finally:
        db_conn.rollback()
