"""FastAPI app entrypoint -- mounts all six read-only routers (PRD §11).

The frontend never calls Socrata/Census/DOB directly; every response here
is a view over the already-ingested Postgres data (CLAUDE.md). No route in
this package writes.

Run locally with: uvicorn api.main:app --reload
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.db import close_pool
from api.routers import activity, parcels, stats
from api.routers import map as map_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_pool()


app = FastAPI(title="Lower Manhattan Development Tracker API", lifespan=lifespan)

# api/ and web/ deploy as two separate Vercel projects (M7) -- api/'s
# internal absolute imports (`from api.db import ...`) need the repo root
# as the deployment root, which doesn't line up with Vercel's single-
# project monorepo convention for a Next.js app + Python functions under
# one root. So this is a genuine cross-origin call in production, not just
# in local dev, and the allowed origin list has to be configurable rather
# than hardcoded to localhost. Set CORS_ALLOWED_ORIGINS (comma-separated)
# on the API's Vercel project once web/ has a real deployment URL;
# defaults to local dev only when unset.
_default_origins = "http://localhost:3000"
allowed_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", _default_origins).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(activity.router)
app.include_router(map_router.router)
app.include_router(parcels.router)
app.include_router(stats.router)
