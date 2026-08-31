"""Pure tests for api.filters -- no network or DB.

ActivityFilters.where_clause() is the piece /api/activity and /api/map both
build their query on, so its SQL/param output is what actually guarantees
the two endpoints return a consistent record set for identical params
(M5's exit criterion) -- these tests lock that contract in directly rather
than only checking it indirectly through the live endpoints.
"""

import pytest
from fastapi import HTTPException

from api.filters import ActivityFilters, _parse_csv_enum


def test_empty_filters_produce_true_with_no_params():
    sql, params = ActivityFilters().where_clause()
    assert sql == "TRUE"
    assert params == []


def test_each_filter_field_adds_its_own_clause_and_param():
    filters = ActivityFilters(
        neighborhood=["Chinatown"],
        category=["new_building", "alteration"],
        source=["dob_now"],
        date_from=None,
        date_to=None,
        cost_min=1000.0,
        cost_max=None,
    )
    sql, params = filters.where_clause()
    assert "neighborhood = ANY(%s)" in sql
    assert "category = ANY(%s)" in sql
    assert "source = ANY(%s)" in sql
    assert "estimated_cost >= %s" in sql
    assert "estimated_cost <= %s" not in sql
    assert params == [["Chinatown"], ["new_building", "alteration"], ["dob_now"], 1000.0]


def test_where_clause_params_are_ordered_to_match_the_sql_placeholders():
    """Since %s placeholders are positional, param order must track clause order exactly."""
    filters = ActivityFilters(date_from=None, cost_min=5.0, neighborhood=["Two Bridges"])
    sql, params = filters.where_clause()
    clauses = sql.split(" AND ")
    assert len(clauses) == len(params)
    assert clauses[0].startswith("neighborhood")
    assert clauses[1].startswith("estimated_cost >=")


def test_parse_csv_enum_splits_and_strips():
    assert _parse_csv_enum("a, b ,c", {"a", "b", "c"}, "x") == ["a", "b", "c"]


def test_parse_csv_enum_returns_none_for_none_input():
    assert _parse_csv_enum(None, {"a"}, "x") is None


def test_parse_csv_enum_rejects_unknown_values():
    with pytest.raises(HTTPException) as exc_info:
        _parse_csv_enum("a,bogus", {"a", "b"}, "category")
    assert exc_info.value.status_code == 422
    assert "bogus" in exc_info.value.detail
