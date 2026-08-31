"""FastAPI app entrypoint -- mounts all six read-only routers (PRD §11).

The frontend never calls Socrata/Census/DOB directly; every response here
is a view over the already-ingested Postgres data (CLAUDE.md). No route in
this package writes.

Run locally with: uvicorn api.main:app --reload
"""

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

# Local dev only: web/ (Next.js on :3000) and api/ (uvicorn, typically :8000)
# are separate processes here. In production both are Vercel functions on
# one domain (Architecture decision, IMPLEMENTATION_PLAN.md §2), so this
# doesn't need to widen beyond localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(activity.router)
app.include_router(map_router.router)
app.include_router(parcels.router)
app.include_router(stats.router)
