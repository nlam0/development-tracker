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
