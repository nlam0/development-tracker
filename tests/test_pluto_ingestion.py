"""Integration checks for the M3 PLUTO ingestion against the live database.

Skipped automatically when SUPABASE_DB_URL_DIRECT isn't configured (see
tests/conftest.py). These lock in the invariants pipeline/sources/pluto.py
depends on: parcels covers exactly the M1-resolved study-area BBL set (no
adapter-side leakage or under-fetching), every row has a usable point
geometry, and the PLUTO version stays pinned per decision D3.
"""


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


def test_parcels_have_no_null_geometry(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM parcels WHERE geom IS NULL;")
        assert cur.fetchone()[0] == 0


def test_parcels_bbl_is_canonical_ten_digit(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM parcels WHERE bbl !~ '^[0-9]{10}$';")
        assert cur.fetchone()[0] == 0


def test_parcels_pluto_version_is_pinned(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT pluto_version FROM parcels;")
        versions = {row[0] for row in cur.fetchall()}
    assert versions == {"26v2"}


def test_most_recent_pluto_ingestion_run_succeeded(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT status, records_rejected FROM ingestion_runs
            WHERE source = 'pluto' ORDER BY started_at DESC LIMIT 1;
        """)
        row = cur.fetchone()
    assert row is not None, "no pluto ingestion_runs row found -- has M3 been run?"
    status, records_rejected = row
    assert status == "success"
    assert records_rejected == 0
