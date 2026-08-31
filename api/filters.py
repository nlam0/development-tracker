"""Shared query-param filter grammar for /api/activity and /api/map (PRD §7B).

The PRD requires filters to update the feed and the map simultaneously, so
the parsing, validation, and SQL WHERE-clause construction for the filter
set they share (neighborhood, date range, category, cost, source) live
here once rather than being duplicated per router. Sort mode and cursor
pagination are feed-only (PRD §7A) and stay in api/routers/activity.py.
"""

from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, Query

VALID_NEIGHBORHOODS = {"Chinatown", "Two Bridges", "Lower East Side"}
VALID_CATEGORIES = {"new_building", "alteration", "demolition", "other"}
VALID_SOURCES = {"dob_now", "dob_legacy"}


def _parse_csv_enum(value: str | None, valid: set[str], param_name: str) -> list[str] | None:
    if value is None:
        return None
    items = [v.strip() for v in value.split(",") if v.strip()]
    bad = sorted(set(items) - valid)
    if bad:
        raise HTTPException(
            422, f"invalid {param_name}: {', '.join(bad)}; expected one of {sorted(valid)}"
        )
    return items or None


@dataclass
class ActivityFilters:
    """The filter set /api/activity and /api/map both accept and apply identically."""

    neighborhood: list[str] | None = None
    category: list[str] | None = None
    source: list[str] | None = None
    block: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    cost_min: float | None = None
    cost_max: float | None = None

    def where_clause(self) -> tuple[str, list]:
        """SQL for a `permits`-table WHERE clause plus its ordered params.

        Returns "TRUE" (no params) when no filter is set, so callers can
        always interpolate the result without a separate empty-filter case.
        """
        clauses: list[str] = []
        params: list = []
        if self.neighborhood:
            clauses.append("neighborhood = ANY(%s)")
            params.append(self.neighborhood)
        if self.category:
            clauses.append("category = ANY(%s)")
            params.append(self.category)
        if self.source:
            clauses.append("source = ANY(%s)")
            params.append(self.source)
        if self.block:
            clauses.append("substring(bbl from 2 for 5) = %s")
            params.append(self.block)
        if self.date_from:
            clauses.append("event_date >= %s")
            params.append(self.date_from)
        if self.date_to:
            clauses.append("event_date <= %s")
            params.append(self.date_to)
        if self.cost_min is not None:
            clauses.append("estimated_cost >= %s")
            params.append(self.cost_min)
        if self.cost_max is not None:
            clauses.append("estimated_cost <= %s")
            params.append(self.cost_max)
        return (" AND ".join(clauses) if clauses else "TRUE"), params


def get_activity_filters(
    neighborhood: str | None = Query(
        None, description="comma-separated: Chinatown,Two Bridges,Lower East Side"
    ),
    category: str | None = Query(
        None, description="comma-separated: new_building,alteration,demolition,other"
    ),
    source: str | None = Query(None, description="comma-separated: dob_now,dob_legacy"),
    block: str | None = Query(
        None, description="5-digit BBL block (chars 2-6), e.g. from a watchlist entry"
    ),
    date_from: date | None = Query(None, description="event_date >= this (inclusive)"),
    date_to: date | None = Query(None, description="event_date <= this (inclusive)"),
    cost_min: float | None = Query(None, ge=0),
    cost_max: float | None = Query(None, ge=0),
) -> ActivityFilters:
    if block is not None and (len(block) != 5 or not block.isdigit()):
        raise HTTPException(422, f"block must be a 5-digit string, got {block!r}")
    return ActivityFilters(
        neighborhood=_parse_csv_enum(neighborhood, VALID_NEIGHBORHOODS, "neighborhood"),
        category=_parse_csv_enum(category, VALID_CATEGORIES, "category"),
        source=_parse_csv_enum(source, VALID_SOURCES, "source"),
        block=block,
        date_from=date_from,
        date_to=date_to,
        cost_min=cost_min,
        cost_max=cost_max,
    )
