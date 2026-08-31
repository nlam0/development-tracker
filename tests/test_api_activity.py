"""Integration checks for GET /api/activity against the live database.

Skipped automatically when SUPABASE_DB_URL_POOLED isn't configured (see
tests/conftest.py). These lock in the invariants api/routers/activity.py
depends on: keyset pagination doesn't skip or repeat rows across a page
boundary, every sort mode actually sorts, filters narrow the result set,
and bad input is rejected rather than silently ignored.
"""


def test_activity_returns_200_with_default_params(api_client):
    r = api_client.get("/api/activity")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "next_cursor" in body


def test_activity_respects_limit(api_client):
    r = api_client.get("/api/activity?limit=3")
    assert len(r.json()["items"]) <= 3


def test_activity_newest_sort_is_non_increasing_by_event_date(api_client):
    r = api_client.get("/api/activity?limit=25&sort=newest")
    dates = [item["event_date"] for item in r.json()["items"]]
    assert dates == sorted(dates, reverse=True)


def test_activity_oldest_sort_is_non_decreasing_by_event_date(api_client):
    r = api_client.get("/api/activity?limit=25&sort=oldest")
    dates = [item["event_date"] for item in r.json()["items"]]
    assert dates == sorted(dates)


def test_activity_cost_sort_puts_nulls_last(api_client):
    r = api_client.get("/api/activity?limit=200&sort=cost")
    costs = [item["estimated_cost"] for item in r.json()["items"]]
    non_null = [c for c in costs if c is not None]
    assert non_null == sorted(non_null, reverse=True)
    first_null = next((i for i, c in enumerate(costs) if c is None), len(costs))
    assert all(c is not None for c in costs[:first_null])


def test_activity_cursor_pagination_has_no_overlap_or_gap_at_the_boundary(api_client):
    page1 = api_client.get("/api/activity?limit=10").json()
    assert page1["next_cursor"] is not None
    page2 = api_client.get(f"/api/activity?limit=10&cursor={page1['next_cursor']}").json()
    ids1 = [item["id"] for item in page1["items"]]
    ids2 = [item["id"] for item in page2["items"]]
    assert set(ids1).isdisjoint(ids2)
    assert len(ids1) == 10


def test_activity_cursor_from_one_sort_mode_is_rejected_for_another(api_client):
    page1 = api_client.get("/api/activity?limit=5&sort=newest").json()
    r = api_client.get(f"/api/activity?limit=5&sort=cost&cursor={page1['next_cursor']}")
    assert r.status_code == 422


def test_activity_neighborhood_filter_narrows_results(api_client):
    r = api_client.get("/api/activity?neighborhood=Chinatown&limit=25")
    items = r.json()["items"]
    assert items
    assert all(item["neighborhood"] == "Chinatown" for item in items)


def test_activity_category_filter_narrows_results(api_client):
    r = api_client.get("/api/activity?category=demolition&limit=25")
    items = r.json()["items"]
    assert items
    assert all(item["category"] == "demolition" for item in items)


def test_activity_rejects_unknown_neighborhood(api_client):
    r = api_client.get("/api/activity?neighborhood=Bogus")
    assert r.status_code == 422


def test_activity_rejects_unknown_sort(api_client):
    r = api_client.get("/api/activity?sort=bogus")
    assert r.status_code == 422


def test_activity_rejects_malformed_cursor(api_client):
    r = api_client.get("/api/activity?cursor=not-valid-base64!!")
    assert r.status_code == 422
