"""GET /api/stats -- research digest aggregates over 7/30/90-day windows (PRD §7E).

Returns all three windows in one response, since the digest UI shows them
together ("activity in the past 7 / 30 / 90 days"), not one at a time.
Scoped to `permits` only -- ACRIS transaction activity joins in at M8.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from api.db import get_conn
from api.filters import VALID_NEIGHBORHOODS
from api.models import BlockActivity, DataCoverage, StatsResponse, StatsWindow, TopProject

router = APIRouter()

WINDOW_DAYS = (7, 30, 90)

# The digest windows are anchored to the current date in New York, not to
# the server's local date and not to UTC. `permits.event_date` holds NYC
# calendar dates (DOB issues permits on NYC days), so "the past 7 days"
# has to mean 7 NYC days for the count to mean what a researcher reads it
# as. This was previously `date.today()`, which is whatever timezone the
# process happens to run in: a local uvicorn on Eastern time and a Vercel
# function on UTC computed different window boundaries from the same
# database, so the same digest reported 20 permits locally and 16 in
# production -- the four dated on the boundary day. UTC alone wouldn't fix
# it either; it would just shift the window a day early every evening
# between 20:00 ET and midnight.
NYC = ZoneInfo("America/New_York")


def window_start(window_days: int) -> date:
    """First event_date included in a digest window, anchored to NYC today.

    `window_days - 1`, not `window_days`: the filter is `event_date >= start`
    with no upper bound, so the window includes today, and subtracting the
    full width made a "7 day" window span 8 calendar dates (and 30 -> 31,
    90 -> 91). Against live data that inflated the 7-day permit count from
    13 to 16. A digest that presents itself as quantitative research output
    has to count the number of days it names.
    """
    return datetime.now(NYC).date() - timedelta(days=window_days - 1)


def _window_stats(conn: Connection, window_days: int, neighborhood: str | None) -> StatsWindow:
    since = window_start(window_days)
    where = ["event_date >= %s"]
    params: list = [since]
    if neighborhood:
        where.append("neighborhood = %s")
        params.append(neighborhood)
    where_sql = " AND ".join(where)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                count(*) AS new_permits,
                count(DISTINCT bbl) AS properties_with_activity,
                coalesce(sum(estimated_cost), 0) AS total_estimated_cost,
                count(*) FILTER (WHERE category = 'new_building') AS new_building_permits,
                count(*) FILTER (WHERE category = 'demolition') AS demolition_permits
            FROM permits WHERE {where_sql};
            """,
            params,
        )
        totals = cur.fetchone()

        cur.execute(
            f"""
            SELECT id, bbl, address, category, estimated_cost, event_date
            FROM permits WHERE {where_sql} AND estimated_cost IS NOT NULL
            ORDER BY estimated_cost DESC LIMIT 5;
            """,
            params,
        )
        largest = cur.fetchall()

        cur.execute(
            f"""
            SELECT substring(bbl from 2 for 5) AS block, count(*) AS filings
            FROM permits WHERE {where_sql} AND bbl IS NOT NULL
            GROUP BY substring(bbl from 2 for 5) HAVING count(*) > 1
            ORDER BY filings DESC LIMIT 10;
            """,
            params,
        )
        blocks = cur.fetchall()

    return StatsWindow(
        window_days=window_days,
        new_permits=totals["new_permits"],
        properties_with_activity=totals["properties_with_activity"],
        total_estimated_cost=totals["total_estimated_cost"],
        new_building_permits=totals["new_building_permits"],
        demolition_permits=totals["demolition_permits"],
        largest_projects=[TopProject(**r) for r in largest],
        blocks_with_multiple_filings=[BlockActivity(**r) for r in blocks],
    )


def _coverage(conn: Connection) -> DataCoverage:
    """What the digest is actually able to see, so the UI can say so.

    Deliberately not filtered by neighborhood: coverage is a property of the
    ingested dataset, not of whatever slice the caller is looking at.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT max(event_date) AS latest FROM permits;")
        latest = cur.fetchone()["latest"]
        cur.execute(
            """
            SELECT max(completed_at) AS last_success
            FROM ingestion_runs WHERE status = 'success';
            """
        )
        last_success = cur.fetchone()["last_success"]

    lag = (datetime.now(NYC).date() - latest).days if latest else None
    return DataCoverage(
        latest_event_date=latest,
        last_successful_ingest=last_success,
        reporting_lag_days=lag,
    )


@router.get("/api/stats", response_model=StatsResponse)
def get_stats(
    neighborhood: str | None = Query(None),
    conn: Connection = Depends(get_conn),
) -> StatsResponse:
    if neighborhood is not None and neighborhood not in VALID_NEIGHBORHOODS:
        raise HTTPException(
            422,
            f"invalid neighborhood: {neighborhood!r}; "
            f"expected one of {sorted(VALID_NEIGHBORHOODS)}",
        )
    windows = {str(d): _window_stats(conn, d, neighborhood) for d in WINDOW_DAYS}
    return StatsResponse(
        generated_at=datetime.now(UTC),
        coverage=_coverage(conn),
        windows=windows,
    )
