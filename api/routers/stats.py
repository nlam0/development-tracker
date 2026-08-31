"""GET /api/stats -- research digest aggregates over 7/30/90-day windows (PRD §7E).

Returns all three windows in one response, since the digest UI shows them
together ("activity in the past 7 / 30 / 90 days"), not one at a time.
Scoped to `permits` only -- ACRIS transaction activity joins in at M8.
"""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from api.db import get_conn
from api.filters import VALID_NEIGHBORHOODS
from api.models import BlockActivity, StatsResponse, StatsWindow, TopProject

router = APIRouter()

WINDOW_DAYS = (7, 30, 90)


def _window_stats(conn: Connection, window_days: int, neighborhood: str | None) -> StatsWindow:
    since = date.today() - timedelta(days=window_days)
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
    return StatsResponse(generated_at=datetime.now(UTC), windows=windows)
