"""Integration checks for the M4 DOB NOW ingestion against the live database.

Skipped automatically when SUPABASE_DB_URL_DIRECT isn't configured (see
tests/conftest.py). These lock in the invariants pipeline/sources/dob_now.py
depends on: the (source, external_id) natural key stays unique under the
corrected R1 composite key, a spatial match (D7(b)) never carries a bbl the
FK can't hold, every row has a non-null event_date, and the D6(b)
block-resolved lots actually carry permits.
"""


def test_permits_natural_key_is_unique(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*), count(DISTINCT (source, external_id)) FROM permits;")
        total, distinct = cur.fetchone()
    assert total == distinct
    assert total > 0


def test_spatial_matches_never_carry_a_bbl(db_conn):
    """D7(b): a spatially-matched permit's bbl has no parcels row, so the
    FK can't hold it -- it must be null."""
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM permits WHERE study_area_match = 'spatial' AND bbl IS NOT NULL;"
        )
        assert cur.fetchone()[0] == 0


def test_spatial_matches_recover_the_r12_gap(db_conn):
    """The whole point of D7(b): permits a bbl-only allowlist would drop."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM permits WHERE study_area_match = 'spatial';")
        assert cur.fetchone()[0] > 0


def test_bbl_matched_permits_join_to_parcels(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM permits p
            WHERE p.study_area_match = 'bbl'
              AND p.bbl NOT IN (SELECT bbl FROM parcels);
        """)
        assert cur.fetchone()[0] == 0


def test_event_date_is_never_null(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM permits WHERE event_date IS NULL;")
        assert cur.fetchone()[0] == 0


def test_category_is_never_null(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM permits WHERE category IS NULL;")
        assert cur.fetchone()[0] == 0


def test_category_values_are_canonical(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT category FROM permits;")
        values = {row[0] for row in cur.fetchall()}
    assert values <= {"new_building", "alteration", "demolition", "other"}


def test_permits_on_block_resolved_lots_are_loaded(db_conn):
    """Decision D6(b) exists so parcels like Essex Crossing's centroid-less
    lots can carry permits at all -- verify M4 actually benefits from it."""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM permits p
            JOIN study_area_bbls b ON b.bbl = p.bbl
            WHERE b.resolution_method = 'block_membership';
        """)
        assert cur.fetchone()[0] > 0


def test_most_recent_completed_dob_now_ingestion_run_succeeded(db_conn):
    """The last run that *finished* must have succeeded.

    Scoped to completed runs on purpose. Reading the latest row outright
    made this fail whenever a run happened to be in flight -- which is not
    a defect in the data, just a 21-minute window each morning during which
    the newest row legitimately reads 'running'. CI caught exactly that
    (against a local run, not the cron) and would have flaked daily
    otherwise. An in-flight run is unfinished, not failed; the question
    this asks is whether ingestion is healthy, which only a completed run
    can answer.
    """
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT status, records_rejected FROM ingestion_runs
            WHERE source = 'dob_now' AND status <> 'running'
            ORDER BY started_at DESC LIMIT 1;
        """)
        row = cur.fetchone()
    assert row is not None, "no completed dob_now ingestion_runs row found -- has M4 been run?"
    status, records_rejected = row
    assert status == "success"
    assert records_rejected == 0
