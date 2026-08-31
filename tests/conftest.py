import os

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture(scope="session")
def db_conn():
    db_url = os.environ.get("SUPABASE_DB_URL_DIRECT")
    if not db_url:
        pytest.skip("SUPABASE_DB_URL_DIRECT not set; skipping DB-dependent tests")
    conn = psycopg.connect(db_url, connect_timeout=10)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def api_client():
    """A TestClient for api/main.py, backed by the live pooled connection.

    Skipped gracefully without SUPABASE_DB_URL_POOLED, same as db_conn skips
    without SUPABASE_DB_URL_DIRECT -- M5's API tests hit real endpoints
    against the real database rather than mocking it, matching every other
    DB-dependent test in this suite (see tests/test_dob_now_ingestion.py).
    """
    if not os.environ.get("SUPABASE_DB_URL_POOLED"):
        pytest.skip("SUPABASE_DB_URL_POOLED not set; skipping API tests")
    from fastapi.testclient import TestClient

    from api.db import close_pool
    from api.main import app

    with TestClient(app) as client:
        yield client
    close_pool()
