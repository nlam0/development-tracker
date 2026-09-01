"""Ingestion run bookkeeping and per-table upsert helpers shared by every adapter.

Every adapter's pipeline stage order ends the same way (PRD §8): upsert,
then record the ingestion timestamp. This module owns both, so an adapter's
own code only has to handle what's genuinely source-specific -- fetch,
validate, normalize, filter -- not how a run gets logged or a natural key
gets upserted.
"""

from collections.abc import Iterable

from psycopg.types.json import Jsonb

STALE_RUN_MESSAGE = (
    "superseded by a later run; this run never reported completion "
    "(process killed, timed out, or lost its connection)"
)


def start_run(conn, source: str, *, cursor_start: str | None = None):
    """Insert a 'running' ingestion_runs row and commit it immediately.

    Returns (run_id, started_at). `started_at` is the database clock at
    insert, and this row commits before any upsert opens its transaction --
    which is what makes it a valid "did this run touch that row?" boundary
    for mark_absent_after_full_reload.

    Committed on its own, ahead of any fetch/transform work, so a run that
    crashes mid-fetch still leaves durable evidence it started (Risk R8: a
    cron job that fails silently is worse than no cron job).

    A process killed outright -- a GitHub Actions timeout, an OOM -- never
    reaches finish_run, so its row would otherwise sit at 'running' forever
    and read as healthy. Any such orphan for this source is closed out as
    failed here, on the reasoning that a new run starting means no earlier
    one is still live.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE ingestion_runs
            SET status = 'failed', completed_at = now(), error_message = %s
            WHERE source = %s AND status = 'running';
            """,
            (STALE_RUN_MESSAGE, source),
        )
        cur.execute(
            """
            INSERT INTO ingestion_runs (source, cursor_start, status)
            VALUES (%s, %s, 'running')
            RETURNING id, started_at;
            """,
            (source, cursor_start),
        )
        run_id, started_at = cur.fetchone()
    conn.commit()
    return run_id, started_at


def finish_run(
    conn,
    run_id: int,
    *,
    status: str,
    records_received: int = 0,
    records_inserted: int = 0,
    records_updated: int = 0,
    records_rejected: int = 0,
    records_marked_absent: int = 0,
    cursor_end: str | None = None,
    error_message: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE ingestion_runs
            SET completed_at = now(), status = %s, cursor_end = %s,
                records_received = %s, records_inserted = %s,
                records_updated = %s, records_rejected = %s,
                records_marked_absent = %s, error_message = %s
            WHERE id = %s;
            """,
            (
                status,
                cursor_end,
                records_received,
                records_inserted,
                records_updated,
                records_rejected,
                records_marked_absent,
                error_message,
                run_id,
            ),
        )


def purge_rejected_for_source(conn, source: str) -> int:
    """Clear a full-reload source's previous rejects. Returns rows deleted.

    Only correct for sources that re-fetch their whole record set every run:
    the current run's rejects are then the complete reject set, and keeping
    earlier ones would re-log the same malformed record every day forever.
    Both current adapters qualify -- PLUTO, and DOB NOW, which ended up a
    full reload of the study area's current state rather than the
    `approved_date` cursor M4 originally sketched (see dob_now.py's module
    docstring). A genuinely incremental source must NOT call this: its
    earlier rejects concern records the current run never refetched.
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM rejected_records WHERE source = %s;", (source,))
        return cur.rowcount


def mark_absent_after_full_reload(
    conn, table: str, run_started_at, *, source: str | None = None
) -> int:
    """Flag rows a completed full scan didn't see. Returns rows marked.

    Only correct for a full-reload source, and only after its upserts have
    run: the test is `retrieved_at < run_started_at`, and both upsert
    helpers set `retrieved_at = now()`, so anything still carrying an
    older timestamp is a row this run's fetch did not return.

    `run_started_at` must come from the database clock, not the client's --
    start_run's `started_at` is the value to pass. It commits before any
    upsert opens its transaction, so every row this run touches is stamped
    at or after it.

    That ordering is the whole precondition, and it rests on `now()` being
    transaction start time rather than statement time: rows written in the
    same transaction as start_run share its exact timestamp and the strict
    `<` leaves them alone. Safe in both directions for the adapters (each
    run is its own process), but a caller that seeded rows and started a
    run in one transaction would see nothing marked.

    Marking, not deleting (see db/migrations/0013): a permit that
    disappears from DOB's published set is a finding in its own right, and
    a row that reappears is set current again by the upsert, so this is
    reversible in both directions.
    """
    where = ["retrieved_at < %s", "is_current"]
    params: list = [run_started_at]
    if source is not None:
        where.append("source = %s")
        params.append(source)
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE {table} SET is_current = FALSE WHERE {' AND '.join(where)};",
            params,
        )
        return cur.rowcount


def record_rejected(conn, run_id: int, source: str, rows: Iterable[tuple[str, dict]]) -> None:
    """Log malformed records rather than silently dropping them (PRD §14)."""
    rows = list(rows)
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO rejected_records (run_id, source, reason, raw)
            VALUES (%s, %s, %s, %s);
            """,
            [(run_id, source, reason, Jsonb(raw)) for reason, raw in rows],
        )


PARCEL_COLUMNS = [
    "bbl",
    "borough",
    "block",
    "lot",
    "address",
    "neighborhood",
    "latitude",
    "longitude",
    "zoning",
    "land_use",
    "lot_area",
    "building_area",
    "commercial_area",
    "residential_area",
    "units_residential",
    "units_total",
    "num_buildings",
    "num_floors",
    "year_built",
    "assessed_total",
    "owner_name",
    "census_tract_2020",
    "census_tract_2010",
    "pluto_version",
]


def _count_upsert_results(cur) -> tuple[int, int]:
    """Tally RETURNING (xmax = 0) flags across an executemany result set.

    executemany(returning=True) leaves one result set per input row, walked
    with nextset(). `xmax = 0` distinguishes a fresh insert from a conflict
    that took the DO UPDATE branch.
    """
    inserted = updated = 0
    while True:
        if cur.pgresult is not None and cur.rowcount and cur.rowcount > 0:
            row = cur.fetchone()
            if row is not None:
                if row[0]:
                    inserted += 1
                else:
                    updated += 1
        if not cur.nextset():
            break
    return inserted, updated


def upsert_parcels(conn, rows: Iterable[dict]) -> tuple[int, int]:
    """Upsert into parcels on the bbl primary key. Returns (inserted, updated).

    Also derives `geom` from latitude/longitude and sets `retrieved_at`
    server-side, so callers only supply the PARCEL_COLUMNS fields.

    Batched through executemany rather than a per-row execute loop: against
    Supabase the round trip per row dominates everything else (~72s vs ~0.2s
    for 2,000 rows), which matters once the legacy-permit backfill runs tens
    of thousands of rows through this same pattern.

    Callers must pass at most one row per conflict key -- two rows with the
    same bbl in a single batch raise CardinalityViolation ("ON CONFLICT DO
    UPDATE command cannot affect row a second time").
    """
    rows = list(rows)
    if not rows:
        return 0, 0
    cols = PARCEL_COLUMNS
    placeholders = ", ".join(f"%({c})s" for c in cols)
    update_cols = [c for c in cols if c != "bbl"]
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    # ST_MakePoint and ST_SetSRID are both STRICT, so a null coordinate yields
    # a null geom without a CASE guard. The casts are required, not cosmetic:
    # under executemany the statement is prepared once, and a null parameter
    # carries no type, so an uncast placeholder fails type inference
    # ("could not determine data type of parameter"). Study-area lots admitted
    # by block membership (decision D6(b)) have no PLUTO centroid, so null
    # coordinates are a normal case here, not an edge one.
    sql = f"""
        INSERT INTO parcels ({", ".join(cols)}, geom, retrieved_at)
        VALUES ({placeholders},
                ST_SetSRID(
                    ST_MakePoint(%(longitude)s::float8, %(latitude)s::float8), 4326),
                now())
        ON CONFLICT (bbl) DO UPDATE SET {set_clause}, geom = EXCLUDED.geom,
            retrieved_at = now(), is_current = TRUE
        RETURNING (xmax = 0) AS inserted;
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows, returning=True)
        return _count_upsert_results(cur)


PERMIT_COLUMNS = [
    "source",
    "external_id",
    "bbl",
    "bin",
    "address",
    "filing_number",
    "permit_type",
    "work_type",
    "category",
    "filing_reason",
    "status",
    "description",
    "estimated_cost",
    "approved_date",
    "issued_date",
    "expired_date",
    "event_date",
    "latitude",
    "longitude",
    "owner_name",
    "neighborhood",
    "study_area_match",
]


def upsert_permits(conn, rows: Iterable[dict]) -> tuple[int, int]:
    """Upsert into permits on the (source, external_id) natural key.

    Mirrors upsert_parcels: derives geom from latitude/longitude with casts
    on the STRICT PostGIS constructors (a bare null placeholder fails
    Postgres type inference under executemany -- see upsert_parcels), sets
    retrieved_at server-side, and expects `raw` as a psycopg Jsonb value
    already present on each row dict.

    Callers must pass at most one row per (source, external_id) -- two rows
    sharing a conflict key in one batch raise CardinalityViolation.
    """
    rows = list(rows)
    if not rows:
        return 0, 0
    cols = [*PERMIT_COLUMNS, "raw"]
    placeholders = ", ".join(f"%({c})s" for c in cols)
    update_cols = [c for c in cols if c not in ("source", "external_id")]
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    sql = f"""
        INSERT INTO permits ({", ".join(cols)}, geom, retrieved_at)
        VALUES ({placeholders},
                ST_SetSRID(
                    ST_MakePoint(%(longitude)s::float8, %(latitude)s::float8), 4326),
                now())
        ON CONFLICT (source, external_id) DO UPDATE SET {set_clause}, geom = EXCLUDED.geom,
            retrieved_at = now(), is_current = TRUE
        RETURNING (xmax = 0) AS inserted;
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows, returning=True)
        return _count_upsert_results(cur)
