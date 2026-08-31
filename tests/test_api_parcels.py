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


def test_parcel_permits_returns_only_that_bbls_permits(api_client, db_conn, sample_bbl):
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM permits WHERE bbl = %s;", (sample_bbl,))
        expected = cur.fetchone()[0]
    r = api_client.get(f"/api/parcels/{sample_bbl}/permits?limit=500")
    items = r.json()
    assert r.status_code == 200
    assert len(items) == min(expected, 500)
    assert all(item["bbl"] == sample_bbl for item in items)


def test_parcel_permits_404s_for_unknown_bbl(api_client):
    r = api_client.get("/api/parcels/9999999999/permits")
    assert r.status_code == 404


def test_parcel_records_returns_an_empty_list_before_m8(api_client, sample_bbl):
    """property_records has no ACRIS data loaded yet (M8) -- the endpoint
    should still succeed with an empty list, not error."""
    r = api_client.get(f"/api/parcels/{sample_bbl}/records")
    assert r.status_code == 200
    assert r.json() == []


def test_parcel_records_404s_for_unknown_bbl(api_client):
    r = api_client.get("/api/parcels/9999999999/records")
    assert r.status_code == 404
