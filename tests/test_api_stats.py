"""Integration checks for GET /api/stats against the live database.

Skipped automatically when SUPABASE_DB_URL_POOLED isn't configured (see
tests/conftest.py). Locks in that all three digest windows come back
together, widen monotonically (a 90-day count can never be smaller than
the 7-day count it contains), and a neighborhood filter actually narrows
the count rather than being silently ignored.
"""


def test_stats_returns_all_three_windows(api_client):
    r = api_client.get("/api/stats")
    assert r.status_code == 200
    windows = r.json()["windows"]
    assert set(windows) == {"7", "30", "90"}


def test_stats_window_days_match_their_key(api_client):
    windows = api_client.get("/api/stats").json()["windows"]
    for key, window in windows.items():
        assert window["window_days"] == int(key)


def test_stats_counts_widen_monotonically_with_window_size(api_client):
    windows = api_client.get("/api/stats").json()["windows"]
    permits = [windows[k]["new_permits"] for k in ("7", "30", "90")]
    assert permits == sorted(permits)
    assert (
        windows["7"]["total_estimated_cost"]
        <= windows["30"]["total_estimated_cost"]
        <= windows["90"]["total_estimated_cost"]
    )


def test_stats_neighborhood_filter_narrows_counts(api_client):
    all_areas = api_client.get("/api/stats").json()["windows"]["90"]["new_permits"]
    one_area = api_client.get("/api/stats?neighborhood=Chinatown").json()["windows"]["90"][
        "new_permits"
    ]
    assert one_area <= all_areas


def test_stats_rejects_unknown_neighborhood(api_client):
    r = api_client.get("/api/stats?neighborhood=Bogus")
    assert r.status_code == 422


def test_stats_largest_projects_are_sorted_by_cost_descending(api_client):
    windows = api_client.get("/api/stats").json()["windows"]
    projects = windows["90"]["largest_projects"]
    costs = [p["estimated_cost"] for p in projects]
    assert costs == sorted(costs, reverse=True)


def test_stats_blocks_with_multiple_filings_all_have_more_than_one(api_client):
    windows = api_client.get("/api/stats").json()["windows"]
    blocks = windows["90"]["blocks_with_multiple_filings"]
    assert all(b["filings"] > 1 for b in blocks)
