"""Integration checks for GET /api/map against the live database.

Skipped automatically when SUPABASE_DB_URL_POOLED isn't configured (see
tests/conftest.py). The point of this endpoint sharing api/filters.py with
/api/activity is that identical filter params return a consistent record
set across both (M5's exit criterion) -- test_map_matches_activity_for_the_
same_filters checks that directly, not just that /api/map returns valid
GeoJSON on its own.
"""


def test_map_returns_a_feature_collection(api_client):
    r = api_client.get("/api/map?neighborhood=Chinatown")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"]


def test_map_features_have_point_geometry_matching_lat_long(api_client):
    r = api_client.get("/api/map?limit=10")
    for feature in r.json()["features"]:
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"
        lon, lat = feature["geometry"]["coordinates"]
        assert -74.1 < lon < -73.9
        assert 40.6 < lat < 40.8


def test_map_matches_activity_for_the_same_filters(api_client):
    """Both read the same filtered permits, so under a limit neither page
    truncates, the id sets returned by each endpoint must be identical."""
    activity = api_client.get(
        "/api/activity?neighborhood=Chinatown&category=new_building&limit=200"
    ).json()
    assert activity["next_cursor"] is None, "test assumes this filtered set fits one page"
    map_body = api_client.get("/api/map?neighborhood=Chinatown&category=new_building").json()

    activity_ids = {item["id"] for item in activity["items"]}
    map_ids = {f["properties"]["id"] for f in map_body["features"]}
    assert activity_ids == map_ids


def test_map_rejects_unknown_category(api_client):
    r = api_client.get("/api/map?category=bogus")
    assert r.status_code == 422
