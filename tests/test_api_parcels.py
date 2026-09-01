"""Integration checks for GET /api/parcels/{bbl} and its sub-resources.

Skipped automatically when SUPABASE_DB_URL_POOLED (api_client) or
SUPABASE_DB_URL_DIRECT (db_conn, used only to pick a real BBL to query
against) isn't configured. Locks in that a real BBL returns a real parcel,
an unknown-but-well-formed BBL 404s rather than 500ing, a malformed BBL
422s before ever reaching the database, and the sub-resource routes 404
the same way the parent does -- rather than returning an empty list for a
BBL that was never a parcel at all.
"""

import pytest


@pytest.fixture
def sample_bbl(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT bbl FROM parcels LIMIT 1;")
        return cur.fetchone()[0]


def test_get_parcel_returns_200_for_a_real_bbl(api_client, sample_bbl):
    r = api_client.get(f"/api/parcels/{sample_bbl}")
    assert r.status_code == 200
    assert r.json()["bbl"] == sample_bbl


def test_get_parcel_404s_for_a_well_formed_unknown_bbl(api_client):
    r = api_client.get("/api/parcels/9999999999")
    assert r.status_code == 404


def test_get_parcel_422s_for_a_malformed_bbl(api_client):
    r = api_client.get("/api/parcels/not-a-bbl")
    assert r.status_code == 422


@pytest.fixture
def busiest_bbl(db_conn):
    """The parcel with the most permits -- 555 at the time of writing, well
    past the default page, which is what makes `total` load-bearing."""
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT bbl, count(*) AS n FROM permits WHERE bbl IS NOT NULL
            GROUP BY bbl ORDER BY n DESC LIMIT 1;
            """
        )
        row = cur.fetchone()
        return row[0], row[1]


def test_parcel_permits_returns_only_that_bbls_permits(api_client, db_conn, sample_bbl):
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM permits WHERE bbl = %s;", (sample_bbl,))
        expected = cur.fetchone()[0]
    r = api_client.get(f"/api/parcels/{sample_bbl}/permits?limit=500")
    body = r.json()
    assert r.status_code == 200
    assert len(body["items"]) == min(expected, 500)
    assert body["total"] == expected
    assert all(item["bbl"] == sample_bbl for item in body["items"])


def test_parcel_permits_total_exceeds_the_page_on_a_busy_parcel(api_client, busiest_bbl):
    """The bug this guards: the page rendered its 100-row slice under a
    heading built from the slice's own length, so a parcel with 555 permits
    displayed "555" nowhere and "100" as if it were the record."""
    bbl, count = busiest_bbl
    body = api_client.get(f"/api/parcels/{bbl}/permits").json()
    assert body["total"] == count
    assert len(body["items"]) == 100
    assert body["total"] > len(body["items"])


def test_parcel_permits_total_is_stable_across_pages(api_client, busiest_bbl):
    bbl, count = busiest_bbl
    first = api_client.get(f"/api/parcels/{bbl}/permits?limit=10").json()
    second = api_client.get(f"/api/parcels/{bbl}/permits?limit=10&offset=10").json()
    assert first["total"] == second["total"] == count
    assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in second["items"]})


def test_parcel_permits_offset_past_the_end_still_reports_the_total(api_client, busiest_bbl):
    """An empty page carries no count(*) OVER () to read, so this is the
    fallback COUNT path -- it must not report 0 for a 555-permit parcel."""
    bbl, count = busiest_bbl
    body = api_client.get(f"/api/parcels/{bbl}/permits?offset=100000").json()
    assert body["items"] == []
    assert body["total"] == count


def test_parcel_permits_404s_for_unknown_bbl(api_client):
    r = api_client.get("/api/parcels/9999999999/permits")
    assert r.status_code == 404


def test_parcel_records_returns_an_empty_page_before_m8(api_client, sample_bbl):
    """property_records has no ACRIS data loaded yet (M8) -- the endpoint
    should still succeed with an empty page, not error."""
    r = api_client.get(f"/api/parcels/{sample_bbl}/records")
    assert r.status_code == 200
    assert r.json() == {"items": [], "total": 0}


def test_parcel_records_404s_for_unknown_bbl(api_client):
    r = api_client.get("/api/parcels/9999999999/records")
    assert r.status_code == 404
