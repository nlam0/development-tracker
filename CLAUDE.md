# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

M0–M7 are complete and deployed: study-area definition, schema and migrations, PLUTO ingestion, DOB NOW ingestion, the read API, the frontend, and production deployment. The study area resolves to 1,954 parcels carrying 10,364 DOB NOW permits. `PRD.md` remains the source of truth for scope and intent, but it describes the product, not the code as built — where the two differ, `IMPLEMENTATION_PLAN.md` records the decision and the reason (its milestone sections are written after the fact, not as plans).

Next milestone is **M8 — secondary sources**: DOB legacy, ACRIS, Census ACS. `property_records` and `census_context` exist as empty tables; anything that reads them returns empty today, which is expected, not a bug.

## What this is

Lower Manhattan Development Tracker ("Division"): a research tool that aggregates NYC public property/permitting records (DOB NOW permits, historical DOB permits, PLUTO, ACRIS, Census ACS) into one searchable interface for tracking development activity in Chinatown, Two Bridges, and adjacent Lower Manhattan neighborhoods. Built as research infrastructure for a senior thesis — optimize for a single serious researcher, not a general-purpose real-estate platform. See PRD.md §1-5 for full framing.

## Commands

```bash
# Python (repo root, .venv/ is the local environment)
pip install -e ".[dev]"
pytest                      # 110 tests; 58 skip without DB credentials
ruff check .                # line-length 100, select = E,F,I,UP
python -m pipeline.run --source pluto      # or --source dob_now
python scripts/migrate.py                  # apply db/migrations in order
python scripts/check_db.py                 # connectivity check
uvicorn api.main:app --reload              # local API on :8000

# Frontend (web/)
npm run dev / build / lint  # lint is eslint incl. React Compiler hook rules
```

Most of the test suite is live-database integration, not mocks — `tests/conftest.py` skips those gracefully when `SUPABASE_DB_URL_*` is unset, so a green `pytest` with no credentials has only run 52 pure tests. Check for skips before treating a pass as meaningful.

## Layout

```
pipeline/      ingestion: sources/{pluto,dob_now}.py, transforms/{bbl,dates,money}.py,
               study_area/{build,load}_boundaries.py + resolve.py, socrata.py, load.py, run.py
api/           FastAPI read layer: routers/{activity,map,parcels,stats}.py, filters.py, models.py, db.py
web/           Next.js 16 frontend: app/{,map,parcel/[bbl],watchlist,methodology}, components/, lib/
db/migrations/ numbered .sql, applied in order by scripts/migrate.py
```

`web/AGENTS.md` warns that this Next.js version differs from training data — read `web/node_modules/next/dist/docs/` before writing frontend code.

## Infrastructure

* **Data APIs**: NYC Open Data via Socrata (app token) for DOB NOW / DOB legacy / PLUTO / ACRIS; Census API (key) for ACS.
* **Database**: Supabase Postgres with PostGIS.
* **Deployment**: two separate Vercel projects, deployed by CLI, not connected to GitHub — `division` (`web/`) and `division-api` (repo root, not `api/`, because `api/main.py` uses absolute imports needing the repo root on the path). `nicklam.co/division` is a rewrite from a separate `my-site` project. See README "Deployment" for why auto-deploy was tried and reverted.
* **Scheduled ingestion**: `.github/workflows/ingest.yml`, daily at 09:00 UTC, PLUTO before DOB NOW (`permits.bbl` is an FK to `parcels.bbl`).

Secrets belong in environment variables / GitHub Actions secrets — never hardcode them or commit `.env`.

**Connection strings are not interchangeable** (Risk R7): `SUPABASE_DB_URL_POOLED` (transaction pooler, port 6543) for the serverless API, and `SUPABASE_DB_URL_DIRECT` for ingestion — which despite its name now holds a *session*-pooler string, because GitHub runners have no IPv6 egress and Supabase's literal direct host is IPv6-only. `api/db.py` sets `prepare_threshold=None` and `autocommit=True` for the transaction pooler; those kwargs are load-bearing, not cosmetic.

## Architecture

Two halves that must not become coupled: **ingestion** (Python, scheduled, writes) and **application** (FastAPI + Next.js, reads). The frontend never calls Socrata/Census/DOB directly — everything goes through ingested Postgres and the FastAPI layer. No route in `api/` writes.

### Ingestion invariants

Every adapter follows the same stage order (PRD §8): fetch → validate → normalize → resolve BBL → filter to study area → deduplicate → upsert → record the run. Ingestion must be idempotent — re-running must never duplicate rows (upsert on the natural key: `bbl` for parcels, `source` + `external_id` for permits). Log malformed records to `rejected_records` rather than dropping them; fail the Actions run visibly (non-zero exit) rather than swallowing errors.

Both current adapters are **full reloads** of the study area's current upstream state, not incremental cursors — a permit's status changes after it first appears, and new spatial-only matches require re-scanning the bounding box regardless of cursor position. Full-reload sources call `purge_rejected_for_source`; a future incremental source must not.

`upsert_parcels`/`upsert_permits` batch through `executemany` (~72s vs ~0.2s per 2,000 rows against Supabase) and require **at most one row per conflict key per batch** — duplicates raise `CardinalityViolation`.

### Canonical identifiers

BBL is the primary parcel key everywhere, always a 10-digit **string**, never a number: `borough(1) + block(5) + lot(4)`. Keep each source's native ID in `source` + `external_id`. Do not join on street address unless BBL is genuinely unavailable.

### Data model

`parcels` (one row per BBL), `permits` (many per BBL), `property_records` (ACRIS, empty until M8), `census_context` (keyed by geography, never attached to individual parcels), `study_areas` + `study_area_bbls` (the researcher-defined boundary and its derived BBL allowlist), `ingestion_runs` (audit log), `rejected_records`.

Two membership decisions are recorded per row rather than smoothed away, and code must preserve that: parcels admitted by block membership instead of a centroid carry a weaker `resolution_method` (D6); permits matched by their own point rather than a BBL in the allowlist carry `study_area_match='spatial'` **and a null `bbl`** (D7). A spatially-matched permit therefore appears in the feed and map but has no parcel page — that is by design, not a gap to patch.

### Backend API

Read-only views over ingested data, never passthroughs:

```
GET /api/activity              # feed, filterable, keyset-paginated
GET /api/parcels/{bbl}         # parcel summary (404s on unknown BBL, at every depth)
GET /api/parcels/{bbl}/permits
GET /api/parcels/{bbl}/records
GET /api/map                   # GeoJSON FeatureCollection for markers
GET /api/study-areas           # boundary geometry (added in M6)
GET /api/stats                 # digest aggregates (7/30/90-day windows)
```

`/api/activity` uses keyset, not offset, pagination, keyed on a `(null-rank, value, id)` triple so nullable `estimated_cost` sorts don't silently drop rows. `/api/filters.py`'s `ActivityFilters` is shared by `/api/activity` and `/api/map` so identical params return a consistent set. Digest windows anchor to the current date in **America/New_York**, not UTC or server-local — `permits.event_date` holds NYC calendar dates.

### Frontend

Three views sharing one filter state, which lives in the **URL query string** (`web/lib/filters.ts`), not React context or a store, and whose param names match `api/filters.py` field-for-field. Watchlist is localStorage-only — no auth, no backend persistence. Visual direction is a research instrument, not a startup dashboard: typography, density, fast filtering; avoid gradients, oversized cards, heavy rounding, animation.

## Working norms

This project's documentation is unusually honest about uncertainty, and that is a feature to maintain:

* **State what you did not verify.** If you can't drive a browser, say the UI paths are unverified rather than implying they work.
* **Investigate discrepancies against the database** rather than patching symptoms — several bugs here (the timezone window, `ORDER BY 0`, the category mapping) were found by querying live data, not by reasoning about the code.
* **Record decisions where they'll be found**: `IMPLEMENTATION_PLAN.md` §6 for numbered decisions, inline comments for load-bearing kwargs, `definition_note` for research judgments surfaced on `/methodology`.
* Keep this file current. It was allowed to claim the repo was pre-implementation for seven milestones; that is a bug in the highest-leverage file in the project.

## Scope discipline

V1 excludes (PRD §17): user accounts, payments, social features, mobile apps, AI/generative features, automated zoning interpretation, predictive scoring, all-five-boroughs coverage, valuation models, deep ACRIS interpretation, real-time streaming. Deferred to V1.1 (PRD §18): saved searches, email digests, CSV export, time-period comparison, historical PLUTO snapshots, alerts. If a task seems to call for something in these lists, flag it against the PRD rather than building it.

## Geographic scope

Study-area boundaries (Chinatown, Two Bridges, adjacent Lower East Side) are researcher-defined, not official administrative boundaries, and are stored in `study_areas` — never hardcoded per-query, never copied into frontend code. The UI must state this distinction to users (PRD §5).
