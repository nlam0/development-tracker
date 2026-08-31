# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository is pre-implementation — currently only `PRD.md` (the full product spec) exists. There is no code, package manifest, or build tooling yet. Read `PRD.md` in full before starting any work; it is the source of truth for scope, data model, and UX. Do not invent build/lint/test commands — add them here once the corresponding tooling actually exists in the repo.

## What this is

Lower Manhattan Development Tracker: a research tool that aggregates NYC public property/permitting records (DOB NOW permits, historical DOB permits, PLUTO, ACRIS, Census ACS) into one searchable interface for tracking development activity in Chinatown, Two Bridges, and adjacent Lower Manhattan neighborhoods. Built as research infrastructure for a senior thesis — optimize for a single serious researcher, not a general-purpose real-estate platform. See PRD.md §1-5 for full framing.

## Confirmed infrastructure

* **Data APIs**: NYC Open Data via Socrata (app token available) for DOB NOW / DOB legacy / PLUTO / ACRIS; Census API (key available) for ACS context data.
* **Database**: Supabase (Postgres) — use this instead of a self-hosted PostgreSQL instance when following PRD §10's schema.
* **Backend**: Python + FastAPI (PRD §11).
* **Frontend**: React/Next.js + TypeScript, deployed on Vercel (PRD §12).
* **Mapping**: MapLibre GL JS (PRD §7B, §12).
* **Scheduled ingestion**: GitHub Actions cron (PRD §13) — not a long-running worker.

Secrets (Socrata app token, Census API key, Supabase connection string) belong in environment variables / GitHub Actions secrets — never hardcode them or commit `.env` files.

## Architecture (from PRD — build to this shape)

The system has two independent halves that must not become coupled: **ingestion** (Python, scheduled, writes to Supabase) and **application** (FastAPI + Next.js, reads from Supabase). The frontend never calls Socrata/Census/DOB APIs directly — everything goes through the ingested Postgres data and the FastAPI layer.

### Ingestion pipeline (PRD §8)

One adapter per external source so a schema change in one source (e.g., DOB NOW) cannot break the others:

```
pipeline/
  sources/      # one file per external source: dob_now.py, dob_legacy.py, pluto.py, acris.py, census.py
  transforms/   # shared normalization: addresses.py, bbl.py, geography.py
  load.py       # upsert into Supabase/Postgres
```

Every adapter follows the same pipeline stage order: fetch → validate → normalize → resolve BBL → filter to study area → deduplicate → upsert → record ingestion timestamp. Ingestion must be idempotent — re-running a job must never create duplicate rows (dedupe on `source` + `external_id`, and upsert on the natural key, not insert-only). Log malformed records rather than silently dropping them; retry transient API failures; fail the GitHub Actions run visibly (non-zero exit) if ingestion breaks, rather than swallowing errors.

### Canonical identifiers (PRD §9)

BBL is the primary parcel key everywhere. Always normalize to a 10-digit string: `borough(1) + block(5) + lot(4)`. Keep each source's native external ID in its own column (`source` + `external_id`) rather than overwriting BBL-based joins — do not join on street address unless BBL is genuinely unavailable for that record.

### Data model (PRD §10)

Core tables: `parcels` (PLUTO-derived parcel context, one row per BBL), `permits` (DOB NOW + DOB legacy, many rows per BBL), `property_records` (ACRIS documents, many rows per BBL), `census_context` (neighborhood-level ACS variables, keyed by geography not BBL — never attach Census data to individual parcel profiles), `ingestion_runs` (audit log of each pipeline run: counts received/inserted/updated, status, error_message). `permits` and `property_records` both carry `source` + `external_id` + `retrieved_at` for traceability back to the raw record.

### Backend API (PRD §11)

FastAPI endpoints are read-only views over the ingested data, not passthroughs to upstream APIs:

```
GET /api/activity              # chronological feed, filterable
GET /api/parcels/{bbl}         # parcel summary
GET /api/parcels/{bbl}/permits
GET /api/parcels/{bbl}/records # ACRIS records for a parcel
GET /api/map                   # geo-filtered activity for map markers
GET /api/stats                 # research digest aggregates (7/30/90-day windows)
```

### Frontend (PRD §7, §12)

Three interconnected views sharing one filter state: the development feed (default landing page), the map (MapLibre, clustered markers, category-colored by new building / alteration / demolition / transaction), and per-parcel pages keyed by BBL. Filters (neighborhood, date range, permit type, cost, source) apply to both feed and map simultaneously. The watchlist is client-side only (localStorage) — no auth or backend persistence in V1. Visual direction is a research instrument, not a startup dashboard: prioritize typography, density, and fast filtering; avoid gradients, oversized cards, heavy rounding, and animation.

## Scope discipline

V1 explicitly excludes (PRD §17): user accounts, payments, social features, mobile apps, AI summaries/generative features, automated zoning interpretation, predictive scoring, all-five-boroughs coverage, sophisticated valuation models, deep ACRIS document interpretation, and real-time streaming. Don't build toward these speculatively. Deferred to V1.1 (PRD §18): saved searches, email digests, CSV export, time-period comparison, historical PLUTO snapshots, alerts. If a task seems to call for something in these lists, flag it against the PRD rather than building it.

## Geographic scope

Study-area boundaries (Chinatown, Two Bridges, adjacent Lower East Side) are researcher-defined, not official administrative boundaries, and must be stored explicitly in the application (not hardcoded per-query) — the UI must state this distinction to users (PRD §5).
