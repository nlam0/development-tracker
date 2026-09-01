"""Currency tracking for full-reload sources (db/migrations/0013).

Both adapters re-fetch the study area's whole upstream state every run but
only ever upserted, so a record that disappeared upstream stayed in the
database forever, indistinguishable from one confirmed this morning. These
exercise the reconciliation directly against the live database, in a
transaction that is always rolled back -- the point is the interaction
between `retrieved_at`, the run boundary, and the upsert, which a mock
would simply restate.

Marked `writes_db`, and the only tests in this suite that write: every
other live test reads. `start_run` commits by design (Risk R8 -- a run that
crashes must leave durable evidence it started), so a rollback fixture
cannot contain these; they clean up after themselves by source instead, in
a `finally` so a failure still tidies. CI runs `-m "not writes_db"` against
read-only credentials, so these run locally and are skipped there.

Skipped automatically when SUPABASE_DB_URL_DIRECT isn't configured (see
tests/conftest.py).
"""

import pytest
from psycopg.types.json import Jsonb

from pipeline.load import mark_absent_after_full_reload, start_run, upsert_permits

SOURCE = "test_currency"
OTHER_SOURCE = "test_currency_other"

pytestmark = pytest.mark.writes_db


@pytest.fixture
def scratch_conn(db_conn):
    """A connection whose test rows are deleted afterwards, always.

    Rollback isn't available here: start_run commits its own row on purpose,
    which also commits any permits written before it. So cleanup is an
    explicit delete keyed on the test-only source names, run in a finally --
    a failing assertion must not leave rows in a research database.
    """
    try:
        yield db_conn
    finally:
        db_conn.rollback()
        with db_conn.cursor() as cur:
            cur.execute("DELETE FROM permits WHERE source IN (%s, %s);", (SOURCE, OTHER_SOURCE))
            cur.execute(
                "DELETE FROM ingestion_runs WHERE source IN (%s, %s);", (SOURCE, OTHER_SOURCE)
            )
        db_conn.commit()


def _permit_row(external_id: str, bbl: str) -> dict:
    return {
        "source": SOURCE,
        "external_id": external_id,
        "bbl": bbl,
        "bin": None,
        "address": "1 Test St",
        "filing_number": None,
        "permit_type": None,
        "work_type": None,
        "category": "alteration",
        "filing_reason": None,
        "status": "Issued",
        "description": None,
        "estimated_cost": None,
        "approved_date": None,
        "issued_date": None,
        "expired_date": None,
        "event_date": "2026-01-01",
        "latitude": 40.715,
        "longitude": -73.99,
        "owner_name": None,
        "neighborhood": None,
        "study_area_match": "bbl",
        "raw": Jsonb({}),
    }


@pytest.fixture
def sample_bbl(scratch_conn):
    with scratch_conn.cursor() as cur:
        cur.execute("SELECT bbl FROM parcels LIMIT 1;")
        return cur.fetchone()[0]


def _is_current(conn, external_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT is_current FROM permits WHERE source = %s AND external_id = %s;",
            (SOURCE, external_id),
        )
        return cur.fetchone()[0]


def _backdate(conn, external_id: str) -> None:
    """Age a row as if an earlier run had last seen it.

    Necessary because Postgres `now()` is transaction start time, not
    statement time: seeding a row and starting a run inside one transaction
    stamps both with the identical timestamp, and the sweep's strict `<`
    (correctly) leaves it alone. In production the two are always separate
    transactions -- start_run commits before the upserts open theirs, and
    the previous run was a different process entirely -- so backdating here
    reproduces the real condition rather than working around it.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE permits SET retrieved_at = now() - interval '1 day'
            WHERE source = %s AND external_id = %s;
            """,
            (SOURCE, external_id),
        )


def test_a_row_the_run_did_not_see_is_marked_absent(scratch_conn, sample_bbl):
    conn = scratch_conn
    upsert_permits(conn, [_permit_row("gone-1", sample_bbl), _permit_row("kept-1", sample_bbl)])
    _backdate(conn, "gone-1")
    _backdate(conn, "kept-1")

    # A later run that only returns "kept-1".
    _, run_started_at = start_run(conn, SOURCE)
    upsert_permits(conn, [_permit_row("kept-1", sample_bbl)])
    marked = mark_absent_after_full_reload(conn, "permits", run_started_at, source=SOURCE)

    assert marked >= 1
    assert _is_current(conn, "gone-1") is False
    assert _is_current(conn, "kept-1") is True


def test_a_returning_row_is_restored_to_current(scratch_conn, sample_bbl):
    """Marking is reversible in both directions -- the upsert sets
    is_current back to TRUE, so a permit that reappears upstream doesn't
    stay flagged as absent forever."""
    conn = scratch_conn
    upsert_permits(conn, [_permit_row("flaky-1", sample_bbl)])
    _backdate(conn, "flaky-1")
    _, run_started_at = start_run(conn, SOURCE)
    mark_absent_after_full_reload(conn, "permits", run_started_at, source=SOURCE)
    assert _is_current(conn, "flaky-1") is False

    upsert_permits(conn, [_permit_row("flaky-1", sample_bbl)])
    assert _is_current(conn, "flaky-1") is True


def test_marking_is_scoped_to_the_source_that_ran(scratch_conn, sample_bbl):
    """permits holds DOB NOW and (from M8) DOB legacy. A DOB NOW run
    re-fetched only its own set, so an unscoped sweep would mark every
    legacy permit absent the first time DOB NOW ran."""
    conn = scratch_conn
    upsert_permits(conn, [_permit_row("other-source-1", sample_bbl)])
    _backdate(conn, "other-source-1")
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE permits SET source = %s WHERE source = %s AND external_id = %s;",
            (OTHER_SOURCE, SOURCE, "other-source-1"),
        )

    _, run_started_at = start_run(conn, SOURCE)
    mark_absent_after_full_reload(conn, "permits", run_started_at, source=SOURCE)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT is_current FROM permits WHERE source = %s AND external_id = %s;",
            (OTHER_SOURCE, "other-source-1"),
        )
        assert cur.fetchone()[0] is True


def test_marking_is_idempotent(scratch_conn, sample_bbl):
    """Re-running the sweep must not re-count rows it already marked --
    records_marked_absent is an alarm signal (Risk R8), so it has to mean
    "went missing in this run", not "is missing"."""
    conn = scratch_conn
    upsert_permits(conn, [_permit_row("gone-2", sample_bbl)])
    _backdate(conn, "gone-2")
    _, run_started_at = start_run(conn, SOURCE)
    first = mark_absent_after_full_reload(conn, "permits", run_started_at, source=SOURCE)
    second = mark_absent_after_full_reload(conn, "permits", run_started_at, source=SOURCE)

    assert first >= 1
    assert second == 0


def test_start_run_started_at_precedes_upserts_in_the_same_run(scratch_conn, sample_bbl):
    """The whole mechanism rests on this ordering: start_run commits before
    any upsert opens its transaction, so a row this run touched always
    carries retrieved_at >= started_at and survives the sweep."""
    conn = scratch_conn
    _, run_started_at = start_run(conn, SOURCE)
    upsert_permits(conn, [_permit_row("fresh-1", sample_bbl)])

    with conn.cursor() as cur:
        cur.execute(
            "SELECT retrieved_at >= %s FROM permits WHERE source = %s AND external_id = %s;",
            (run_started_at, SOURCE, "fresh-1"),
        )
        assert cur.fetchone()[0] is True
