"""GET /api/activity -- chronological feed, filterable, cursor-paginated (PRD §7A).

Keyset (not offset) pagination: a cursor encodes the last row's position in
the current sort order, so pages stay stable while new permits are ingested
underneath the feed. `estimated_cost` is nullable, and a raw tuple
comparison against a NULL is itself NULL in Postgres -- never true -- which
would silently drop every null-cost row from every page after the first
under `sort=cost`. Every sort mode is therefore keyed on a
(null-rank, value, id) triple: rank is 0 for a present value and 1 for
NULL, so NULLs always sort last regardless of comparison direction, and
every component the keyset predicate compares is guaranteed non-null.
"""

import base64
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from api.db import get_conn
from api.filters import ActivityFilters, get_activity_filters
from api.models import ActivityFeedResponse, PermitOut

router = APIRouter()

SORT_MODES = {"newest", "oldest", "cost"}

PERMIT_COLUMNS = """
    id, source, external_id, bbl, neighborhood, study_area_match, bin, address,
    filing_number, permit_type, work_type, category, filing_reason, status,
    description, estimated_cost, approved_date, issued_date, expired_date,
    event_date, latitude, longitude, owner_name, retrieved_at
"""


def _sort_exprs(sort: str) -> tuple[str, str, str]:
    """Return (rank_expr, value_expr, direction) for a feed sort mode.

    rank_expr is a cast literal (`0::int`), not a bare `0` -- Postgres
    treats a bare integer in ORDER BY as an ordinal column reference, not
    a literal value, and this query has no first select-list column that
    ordinal would be valid against.
    """
    if sort == "newest":
        return "0::int", "event_date", "DESC"
    if sort == "oldest":
        return "0::int", "event_date", "ASC"
    if sort == "cost":
        return "(estimated_cost IS NULL)::int", "COALESCE(estimated_cost, 0)", "DESC"
    raise HTTPException(422, f"invalid sort: {sort!r}; expected one of {sorted(SORT_MODES)}")


def _encode_cursor(sort: str, rank: int, value: date | float, row_id: int) -> str:
    payload = json.dumps({"sort": sort, "rank": rank, "value": str(value), "id": row_id})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(token: str, sort: str) -> tuple[int, date | float, int]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(token.encode()))
        if payload["sort"] != sort:
            raise ValueError("cursor was issued for a different sort mode")
        rank = int(payload["rank"])
        row_id = int(payload["id"])
        raw_value = payload["value"]
        value: date | float
        value = date.fromisoformat(raw_value) if sort in ("newest", "oldest") else float(raw_value)
        return rank, value, row_id
    except Exception as exc:
        raise HTTPException(422, f"invalid cursor: {exc}") from exc


@router.get("/api/activity", response_model=ActivityFeedResponse)
def get_activity(
    filters: ActivityFilters = Depends(get_activity_filters),
    sort: str = Query("newest"),
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    conn: Connection = Depends(get_conn),
) -> ActivityFeedResponse:
    rank_expr, value_expr, direction = _sort_exprs(sort)
    where_sql, params = filters.where_clause()

    seek_sql = ""
    if cursor is not None:
        rank_c, value_c, id_c = _decode_cursor(cursor, sort)
        op = "<" if direction == "DESC" else ">"
        seek_sql = (
            f" AND ({rank_expr} > %s OR "
            f"({rank_expr} = %s AND ({value_expr}, id) {op} (%s, %s)))"
        )
        params = params + [rank_c, rank_c, value_c, id_c]

    sql = f"""
        SELECT {PERMIT_COLUMNS}
        FROM permits
        WHERE {where_sql}{seek_sql}
        ORDER BY {rank_expr} ASC, {value_expr} {direction}, id {direction}
        LIMIT %s;
    """
    with conn.cursor() as cur:
        cur.execute(sql, params + [limit + 1])
        rows = cur.fetchall()

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        if sort == "cost":
            rank_val = 1 if last["estimated_cost"] is None else 0
            value_val: date | float = (
                0 if last["estimated_cost"] is None else last["estimated_cost"]
            )
        else:
            rank_val = 0
            value_val = last["event_date"]
        next_cursor = _encode_cursor(sort, rank_val, value_val, last["id"])

    return ActivityFeedResponse(items=[PermitOut(**r) for r in rows], next_cursor=next_cursor)
