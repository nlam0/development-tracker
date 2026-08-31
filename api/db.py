"""Pooled Postgres connection for the API (Risk R7).

FastAPI on Vercel means many short-lived function instances, so this
connects through Supabase's transaction-mode pooler (port 6543), not the
direct port ingestion uses. Two settings matter specifically because of
that pooler mode, not just because connections are pooled:

- autocommit=True: every request here does a single read, so there's no
  reason to hold a connection idle-in-transaction against a pooler that's
  meant to keep handing connections back out between statements.
- prepare_threshold=None: psycopg normally promotes a repeated query to a
  server-side prepared statement after a few executions. Under pgbouncer's
  transaction-pooling mode, a "prepared" logical connection can be handed
  a different backend between requests, so a later execute can fail with
  "prepared statement does not exist." Supabase's own pooler docs call
  this out; disabling autoprepare avoids it entirely.
"""

import os
from collections.abc import Iterator

from dotenv import load_dotenv
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

load_dotenv()

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        db_url = os.environ.get("SUPABASE_DB_URL_POOLED")
        if not db_url:
            raise RuntimeError(
                "SUPABASE_DB_URL_POOLED is not set. Copy .env.example to .env and fill it in."
            )
        _pool = ConnectionPool(
            db_url,
            min_size=1,
            max_size=5,
            kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": None},
            open=True,
        )
    return _pool


def get_conn() -> Iterator[Connection]:
    with get_pool().connection() as conn:
        yield conn


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
