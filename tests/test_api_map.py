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


def test_map_reports_truncation_when_the_cap_bites(api_client):
    """The bug this guards: a capped response used to be indistinguishable
    from a complete one, so the map presented 5,000 of 10,364 permits as
    the whole study area."""
    body = api_client.get("/api/map?limit=10").json()
    assert len(body["features"]) == 10
    assert body["total"] > 10
    assert body["truncated"] is True


def test_map_reports_no_truncation_when_everything_fits(api_client):
    body = api_client.get("/api/map?neighborhood=Chinatown&category=demolition").json()
    assert body["truncated"] is False
    assert body["total"] == len(body["features"])


def test_map_bbox_restricts_to_the_viewport(api_client):
    """A viewport query must be a strict subset of the unfiltered set, and
    every point it returns must actually lie inside the box."""
    west, south, east, north = -73.999, 40.713, -73.993, 40.718
    body = api_client.get(f"/api/map?bbox={west},{south},{east},{north}").json()
    assert body["features"]
    for feature in body["features"]:
        lon, lat = feature["geometry"]["coordinates"]
        assert west <= lon <= east
        assert south <= lat <= north

    unbounded = api_client.get("/api/map").json()
    assert body["total"] < unbounded["total"]


def test_map_bbox_outside_the_study_area_is_empty_not_an_error(api_client):
    body = api_client.get("/api/map?bbox=-80.0,35.0,-79.0,36.0").json()
    assert body["features"] == []
    assert body["total"] == 0
    assert body["truncated"] is False


def test_map_bbox_composes_with_the_shared_filters(api_client):
    """bbox is map-only, but it has to narrow the same filtered set the feed
    would produce, not replace it."""
    bbox = "-74.02,40.70,-73.97,40.73"
    both = api_client.get(f"/api/map?bbox={bbox}&category=demolition").json()
    box_only = api_client.get(f"/api/map?bbox={bbox}").json()
    assert both["total"] <= box_only["total"]
    assert all(f["properties"]["category"] == "demolition" for f in both["features"])


def test_map_rejects_malformed_bbox(api_client):
    for bad in [
        "1,2,3",  # wrong arity
        "a,b,c,d",  # not numbers
        "-73.99,40.71,-74.02,40.73",  # west >= east
        "-73.99,40.73,-73.97,40.71",  # south >= north
        "-200,40,-73,41",  # longitude out of range
        "-74,40,-73,100",  # latitude out of range
    ]:
        assert api_client.get(f"/api/map?bbox={bad}").status_code == 422, bad


def test_activity_block_filter_matches_only_that_block(api_client):
    """substring(bbl from 2 for 5) is the block portion (Risk-adjacent
    addition -- see api/filters.py); every returned permit's bbl must carry
    exactly the requested block."""
    r = api_client.get("/api/activity?block=00277&limit=50")
    items = r.json()["items"]
    assert items
    assert all(item["bbl"][1:6] == "00277" for item in items)


def test_activity_rejects_malformed_block(api_client):
    r = api_client.get("/api/activity?block=abc")
    assert r.status_code == 422


def test_study_areas_returns_the_three_named_areas(api_client):
    r = api_client.get("/api/study-areas")
    assert r.status_code == 200
    body = r.json()
    names = {f["properties"]["name"] for f in body["features"]}
    assert names == {"Chinatown", "Two Bridges", "Lower East Side"}


def test_study_areas_geometry_is_a_multipolygon(api_client):
    body = api_client.get("/api/study-areas").json()
    assert all(f["geometry"]["type"] == "MultiPolygon" for f in body["features"])
