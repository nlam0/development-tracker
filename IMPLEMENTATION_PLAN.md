# Implementation Plan — Lower Manhattan Development Tracker

Companion to `PRD.md`. The PRD defines *what* and *why*; this document defines *how*, in what order, and what is likely to go wrong. Section references like (PRD §8) point back to the spec.

**Status:** M0-M3 complete, plus a post-M3 data-integrity audit (findings folded into R1 and R12; decisions D6 and D7 resolved and implemented). The study area resolves to **1,954 parcels** (Chinatown 501, Two Bridges 523, Lower East Side 930), all loaded into `parcels`. M0 scaffolding and M1's study areas are committed and pushed (`origin/main`); M1's resolved BBL set is 1,944 parcels (Chinatown 501, Two Bridges 522, Lower East Side 921). M2 has applied the full §3 schema to Supabase -- 9 application tables with all constraints and indexes verified. M3 has loaded all 1,944 study-area parcels from PLUTO into `parcels`, verified idempotent. See each milestone section below for details.

All dataset IDs, field names, and data-quality findings below were verified against the live NYC Open Data API on 2026-08-31. See [Appendix A](#appendix-a--verified-source-reconnaissance) for the raw findings.

---

## 1. Architecture

Two halves that share a database and nothing else (PRD §8). This is the single most important structural rule: the ingestion side may be rewritten wholesale without touching the application side, and the frontend has no knowledge that Socrata exists.

```
   NYC Open Data (Socrata)          Census API
   DOB NOW · DOB legacy                 ACS5
   PLUTO · ACRIS                          │
        │                                 │
        └──────────────┬──────────────────┘
                       ▼
            ┌─────────────────────┐
            │  pipeline/  (Python)│   GitHub Actions, daily cron
            │  fetch → validate → │   idempotent upserts
            │  normalize → BBL →  │   writes ingestion_runs audit row
            │  study-area filter →│
            │  dedupe → upsert    │
            └──────────┬──────────┘
                       ▼
            ┌─────────────────────┐
            │ Supabase (Postgres) │   canonical store; PostGIS for study area
            └──────────┬──────────┘
                       ▼
            ┌─────────────────────┐
            │  api/  (FastAPI)    │   read-only; filtering + pagination
            └──────────┬──────────┘
                       ▼
            ┌─────────────────────┐
            │  web/  (Next.js)    │   feed · map · parcel · methodology
            │  MapLibre GL JS     │   watchlist in localStorage
            └─────────────────────┘
```

**Non-negotiable boundaries**

- The frontend never calls Socrata, Census, or DOB directly. Every byte the user sees came through Postgres.
- The API is read-only. No endpoint triggers ingestion, and no request path performs a write.
- Ingestion never reads from the API layer. It talks to Postgres directly.
- Source-specific vocabulary (`permit_si_no`, `job_filing_number`, `bct2020`) stops at the adapter boundary. Everything downstream speaks the canonical schema.

### Proposed repository layout

```
pipeline/
  sources/            dob_now.py, dob_legacy.py, pluto.py, acris.py, census.py
  transforms/         bbl.py, addresses.py, geography.py, dates.py, money.py
  study_area/         boundaries.geojson, resolve.py
  socrata.py          shared client: app token, paging, retry, backoff
  load.py             upsert helpers + ingestion_runs bookkeeping
  run.py              CLI entrypoint: `python -m pipeline.run --source dob_now`
api/
  main.py             FastAPI app
  routers/            activity.py, parcels.py, map.py, stats.py
  db.py               connection pooling
  models.py           Pydantic response models
  filters.py          shared query-param parsing (feed and map share one filter grammar)
web/
  app/                Next.js App Router: /, /map, /parcel/[bbl], /watchlist, /methodology
  components/
  lib/
db/
  migrations/         numbered SQL migrations
.github/workflows/
  ingest.yml          daily cron
```

### Backend hosting decision

The PRD specifies Vercel for the frontend (PRD §12) but does not say where FastAPI runs. Two viable options:

| Option | Pros | Cons |
|---|---|---|
| **A. FastAPI as Vercel Python serverless functions** (recommended for V1) | One repo, one deploy, one domain, no CORS, no extra bill | Cold starts; strict need for pooled DB connections |
| B. Separate host (Render / Fly.io) | Long-lived process, simple connection pooling | Second deploy target, CORS config, likely a second bill |

**Recommendation: A.** Traffic is one researcher plus occasional visitors; cold starts are acceptable and the operational simplicity is worth more. This choice makes connection pooling mandatory rather than optional — see Risk R7.

---

## 2. Milestones

Sequenced so each milestone leaves the project in a demonstrable state, and so the highest-uncertainty work (study-area definition, BBL joins) happens before anything is built on top of it. Milestones 1–7 constitute PRD §16's V1 success criteria.

### M0 — Foundation
`git init`, `.gitignore` (must cover `.env*`), README skeleton, Python project (`pyproject.toml`, ruff + pytest), Next.js + TypeScript app, `.env.example` documenting `SOCRATA_APP_TOKEN`, `CENSUS_API_KEY`, `SUPABASE_DB_URL`. Verify Supabase connectivity from a script.

**Exit:** `pytest` and `next build` both run clean on empty scaffolding; a script reads and prints the Postgres server version.

### M1 — Study-area definition
Everything downstream filters on this, so it comes first. Enable PostGIS in Supabase and load boundaries into `study_areas`.

**Approach (decision D1): official NTA 2020 geometry as the base, hand-split into three areas.** Take the NTA 2020 polygons for `Chinatown-Two Bridges` and `Lower East Side`, then divide the former into separate Chinatown and Two Bridges polygons along a documented dividing line. This keeps the PRD §5 three-area framing intact — Chinatown and Two Bridges stay independently filterable in feed and map — while resting on citable official geography rather than freehand drawing.

The split line is a research judgment and must be recorded as such: `study_areas.definition_note` carries the rationale verbatim and `/methodology` reproduces it. This is exactly the "research definitions, not official boundaries" caveat PRD §5 requires the UI to state.

Derive the authoritative BBL set by point-in-polygon against PLUTO centroids and materialize it. Deriving from geometry — rather than hardcoding block numbers — keeps the boundary a single editable artifact and makes the study area reproducible.

**Exit:** `study_areas` holds 3 named polygons with populated `definition_note`; a query returns the BBL set per neighborhood; boundaries render in a scratch MapLibre page and visibly follow NTA edges except at the documented split.

**Done.** `pipeline/study_area/build_boundaries.py` reproduces `boundaries.geojson` from source (NTA 2020 dataset `9nt8-h7nd` + NYC DOT LION centerline `inkn-q76z`, filtered to `full_street_name='DIVISION ST'` in Manhattan) rather than treating the split as a one-off hand edit — re-running it is a full source-to-artifact rebuild and was verified to reproduce byte-identical geometry. The Chinatown/Two Bridges split line (flagged as still-to-specify in §6) is the Division Street centerline: Chinatown is the portion north of it, Two Bridges south, toward the bridge approaches. `pipeline/study_area/load_boundaries.py` upserts the artifact into `study_areas`; `pipeline/study_area/resolve.py` derives the BBL allowlist via PostGIS `ST_Contains` against PLUTO centroids and materializes it into `study_area_bbls` (added to the schema in §3, migration `0003_study_area_bbls.sql`).

The resolved BBL set is **1,944 parcels** (Chinatown 501, Two Bridges 522, Lower East Side 921) against a 4,246-parcel bounding-box candidate pool — smaller than the ~3–4k figure M3 estimated from the looser "Manhattan blocks 100–400" reconnaissance query, because the actual study-area polygons are tighter than that block range. **M3's exit criterion below should be read as ~1,900–2,000 parcels**, not 3–4k.

Verification: geometry validity, the split's area-partition property (no gaps or overlaps — checked against the source NTA polygon's exact area), and the three-name/definition_note invariants are covered by `tests/test_study_area_boundaries.py` (no network or DB required). Point-in-polygon assignment was additionally checked visually — a matplotlib plot of all three polygons overlaid with the resolved centroids, colored by assigned study area, confirmed clean containment with no cross-boundary leakage (Two Bridges sits correctly south of the Division St line toward the bridge approaches, Chinatown north of it, Lower East Side properly adjacent to the east). A `scripts/scratch/study_area_map.html` MapLibre page also exists per the milestone's literal wording, but wasn't rendered in a browser during this session (no headless browser available) — the matplotlib check substituted as the actual visual verification.

### M2 — Schema and migrations
Apply §3's DDL as numbered migrations. Includes constraints and indexes, not just tables — the unique constraints are what make ingestion idempotent (PRD §14), so they ship with the schema rather than being retrofitted.

**Exit:** migrations apply cleanly to a fresh database; a documented reset path exists.

**Done.** `db/migrations/0004`–`0009` add `parcels`, `permits`, `property_records`, `census_context`, `ingestion_runs`, and `rejected_records`, in FK-safe order on top of M1's `study_areas`/`study_area_bbls`. Applied to the live Supabase instance via `scripts/migrate.py`; re-running is confirmed a no-op. Verified by introspecting `information_schema` directly rather than trusting the SQL files matched what actually landed: all 9 tables exist, the idempotency-critical `UNIQUE (source, external_id)` constraints are present on both `permits` and `property_records`, and every FK matches the pipeline's load order (`permits.bbl` → `parcels.bbl`, `property_records.bbl` → `parcels.bbl`, `parcels.neighborhood` → `study_areas.name`, `rejected_records.run_id` → `ingestion_runs.id`). `tests/test_schema.py` encodes these same checks so they run on every future `pytest` — skipped gracefully (not failed) when `SUPABASE_DB_URL_DIRECT` isn't set, confirmed by temporarily hiding `.env` and re-running.

`scripts/reset_db.py` is the documented reset path — drops all application tables (not the `postgis` extension) and re-runs migrations, gated behind a `--yes-drop-all-data` flag plus a typed host-name confirmation. It was written and reviewed but **not executed** this session: no local Docker/Postgres was available to test a truly from-scratch apply in isolation, and running it against the live instance would have destroyed M1's already-verified boundary/BBL data for a test that additive migrations already covered. The "fresh database" half of the exit criterion is therefore verified in the weaker sense that all 9 tables + constraints now exist correctly on the real target, not in the stronger sense of a from-scratch rebuild — worth doing once a disposable Postgres is available, or the next time a genuine reset is needed for another reason.

### M3 — PLUTO ingestion → `parcels`
PLUTO is the parcel backbone every other source joins against, so it lands before any permit data. Build `pipeline/socrata.py` (token auth, `$limit`/`$offset` paging, retry with backoff) and `transforms/bbl.py` here — both are used by every later adapter. Filter to the M1 BBL set.

**Exit:** ~1,900–2,000 study-area parcels loaded with zoning, land use, lot/building area, year built, units, lat/long (M1's resolved `study_area_bbls` count, not the earlier loose block-range estimate — see M1); re-running changes `records_updated` but not row count. *Final count after decision D6(b): 1,954.*

**Done.** `pipeline/socrata.py` (token auth, deterministic `$order`-based paging, retry with exponential backoff on 429/5xx — Risk R9) and `pipeline/transforms/bbl.py` (canonical-BBL normalization for all four source shapes, plus `parse_bbl()` to derive `borough`/`block`/`lot` back out of the same string stored as the primary key, so those columns can never diverge from `bbl` — Risk R3) are both built here as shared modules, per the milestone's own instruction that every later adapter reuses them. `pipeline/study_area/resolve.py`'s inline BBL normalization (flagged in M1 as a stopgap) was switched over to `normalize_bbl_pluto()` instead of carrying two copies of the same logic forward.

`pipeline/load.py` adds the ingestion-run bookkeeping (`start_run`/`finish_run`, committed independently of the adapter's main work so a mid-fetch crash still leaves a durable "this run started" record — Risk R8) and `upsert_parcels()`, which upserts on the `bbl` primary key via `INSERT ... ON CONFLICT DO UPDATE ... RETURNING (xmax = 0)` to count inserts vs. updates precisely, and derives `geom` from lat/long server-side. `pipeline/sources/pluto.py` fetches Manhattan PLUTO filtered to the pinned `version='26v2'` (decision D3), normalizes every BBL, filters against `study_area_bbls` (the "filter to study area" pipeline stage reading from M1's materialized allowlist, not re-deriving it), and upserts. A `records_received == 0` guard fails the run loudly rather than silently succeeding with an empty table, in case the borough filter or pinned version ever stops matching anything (Risk R10).

Run against the live Supabase instance: first run received 42,504 Manhattan PLUTO rows, matched all 1,944 study-area BBLs, inserted 1,944, rejected 0. Re-running (idempotency check, PRD §16) received the same 42,504 rows, inserted 0, updated all 1,944 — row count unchanged, exactly the exit criterion. Verified directly against the database (not just adapter output): `parcels` row count equals `study_area_bbls` row count; per-neighborhood counts match M1's exactly (Chinatown 501, Two Bridges 522, Lower East Side 921); zero null `geom`; zero malformed BBLs; `pluto_version` is uniformly `'26v2'`; both `ingestion_runs` rows show `status='success'` with `records_rejected=0`. `tests/test_pluto_ingestion.py` (DB-dependent, skips gracefully without credentials — reconfirmed by temporarily hiding `.env`) and `tests/test_bbl_transforms.py` (pure, covers all four normalization shapes plus the `parse_bbl` round trip) encode these checks for every future run.

**Post-M3 audit.** A read-only integrity pass over the loaded data and the sources M4 will touch found one blocking issue and several fixed defects.

Fixed in code: `resolve.py` paged through `pipeline/socrata.py` instead of a bare `$limit=10000` (4,246 of a 10,000 cap — the study area would have silently *shrunk* on crossing it); per-record rejection in `pipeline/sources/pluto.py` via a new pure, unit-testable `process_records()`, so one unparseable value routes that record to `rejected_records` instead of failing the whole 42,504-row run (PRD §14); `start_run()` now closes out orphaned `'running'` rows, which a killed process would otherwise leave looking healthy forever (Risk R8); `purge_rejected_for_source()` stops a daily cron re-logging identical rejects indefinitely (full-reload sources only — incremental sources must not use it); `parcels.neighborhood` gained `ON UPDATE CASCADE` (migration `0010`) so a study area can be renamed rather than needing data surgery; and `upsert_parcels()` moved from a per-row execute loop to a batched `executemany(returning=True)` — measured at ~0.2s vs ~72s per 2,000 rows against Supabase, which is what makes M8's 20-30k-row legacy backfill practical.

Verified behavior-preserving: the paged resolve returns the identical 4,246 candidates and identical per-area counts, and the batched upsert still reports 0 inserted / 1,944 updated on a re-run.

Blocking M4: the natural key in §4/R1 was measurably wrong — see R1 for the numbers. Not fixed in code, because M4's loader doesn't exist yet; the corrected key is now recorded in both places.

Resolved since: D6(b) and D7(b) in §6. D6(b) is implemented — `resolve.py` admits centroid-less lots by unambiguous block membership, recorded in a new `study_area_bbls.resolution_method` column (migration `0011`); all 10 study-area lots were admitted with zero ambiguous blocks, and the allowlist moved from 1,944 to 1,954. D7(b)'s schema landed (`permits.study_area_match` + `permits.neighborhood`, migration `0012`); its adapter logic belongs to M4.

Admitting the D6(b) lots immediately surfaced a latent bug in the new batched upsert: those lots have no coordinates, and under `executemany` the statement is prepared once, so an uncast null placeholder fails Postgres type inference ("could not determine data type of parameter"). The `CASE` guard around the geometry was dropped in favour of casts on strict PostGIS constructors, and `tests/test_pluto_ingestion.py` now covers the null-coordinate path directly.

### M4 — DOB NOW ingestion → `permits`
The primary source (PRD §6). Incremental sync on `approved_date`. Handle the sentinel-value and null-BBL cases from Risk R1/R2. Write `ingestion_runs` rows on every execution including failures.

**Exit:** study-area permits loaded and joined to `parcels`; running the job twice produces zero net new rows (this is the PRD §16 idempotency criterion, proven by test, not assertion).

### M5 — Read API
FastAPI endpoints per PRD §11. Build `filters.py` first: `/api/activity` and `/api/map` must share one filter grammar, because the PRD requires filters to update feed and map simultaneously (PRD §7B). Cursor pagination on the feed.

**Exit:** all six endpoints serve real study-area data; identical filter params return a consistent record set across feed and map.

### M6 — Frontend
Feed (default landing), map, parcel page, watchlist, methodology (PRD §7, §15). One filter state object drives feed and map. Watchlist is localStorage-only. Visual direction per PRD §12: typographic, dense, restrained — no gradients, minimal animation.

**Exit:** a researcher can filter the feed, see the same set on the map, click a marker, and land on a parcel page showing permits and PLUTO context.

### M7 — Scheduling and deploy
GitHub Actions daily cron with secrets; non-zero exit on failure (PRD §13). Deploy web + API to Vercel. Write the README per PRD §19 and fill the methodology page with real limitations discovered during M3–M4.

**Exit:** PRD §16 fully satisfied — scheduled ingestion runs unattended, duplicates do not accumulate, project is public.

### M8 — Secondary sources
Deliberately after V1 is standing, because each adds join complexity without changing the core workflow: DOB legacy (`dobrundate` cursor), ACRIS (two-stage fetch; condo-lot problem — Risk R4), Census ACS at tract level into `census_context`. Research digest `/api/stats` windows.

**Exit:** parcel pages show transaction history; neighborhood context available without Census data ever being attached to an individual parcel (PRD §6).

---

## 3. Database design

Postgres on Supabase. BBL is `CHAR(10)` everywhere — a normalized string, never a number (Risk R3).

```sql
-- Researcher-defined boundaries (PRD §5). Explicitly not official geography.
CREATE TABLE study_areas (
  id           SERIAL PRIMARY KEY,
  name         TEXT NOT NULL UNIQUE,          -- 'Chinatown', 'Two Bridges', 'Lower East Side'
  geom         GEOMETRY(MultiPolygon, 4326) NOT NULL,
  definition_note TEXT NOT NULL,              -- surfaced verbatim on /methodology
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX study_areas_geom_idx ON study_areas USING GIST (geom);

-- The authoritative BBL allowlist, derived from study_areas via point-in-
-- polygon against PLUTO centroids (M1). Every later adapter's "filter to
-- study area" pipeline stage (PRD §8) reads from this table rather than
-- re-deriving or hardcoding the study-area block/BBL set itself.
CREATE TABLE study_area_bbls (
  bbl           CHAR(10) PRIMARY KEY,
  study_area_id INTEGER NOT NULL REFERENCES study_areas(id),
  resolution_method TEXT NOT NULL              -- 'centroid' | 'block_membership' (D6)
    CHECK (resolution_method IN ('centroid', 'block_membership')),
  resolved_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX study_area_bbls_study_area_id_idx ON study_area_bbls (study_area_id);

-- One row per tax lot, from PLUTO.
CREATE TABLE parcels (
  bbl              CHAR(10) PRIMARY KEY,
  borough          SMALLINT NOT NULL,
  block            INTEGER  NOT NULL,
  lot              INTEGER  NOT NULL,
  address          TEXT,
  neighborhood     TEXT REFERENCES study_areas(name) ON UPDATE CASCADE,
  latitude         DOUBLE PRECISION,
  longitude        DOUBLE PRECISION,
  geom             GEOMETRY(Point, 4326),
  zoning           TEXT,             -- zonedist1
  land_use         TEXT,             -- landuse code; label resolved via lookup
  lot_area         INTEGER,
  building_area    INTEGER,
  commercial_area  INTEGER,
  residential_area INTEGER,
  units_residential INTEGER,
  units_total      INTEGER,
  num_buildings    INTEGER,
  num_floors       NUMERIC(5,2),
  year_built       SMALLINT,
  assessed_total   BIGINT,
  owner_name        TEXT,
  census_tract_2020 TEXT,            -- bct2020; joins ACS 2024 (Risk R11)
  census_tract_2010 TEXT,            -- ct2010;  joins ACS 2014 / 2019 (Risk R11)
  pluto_version    TEXT NOT NULL,    -- pinned to '26v2'; PLUTO is a versioned snapshot
  retrieved_at     TIMESTAMPTZ NOT NULL
);
CREATE INDEX parcels_geom_idx ON parcels USING GIST (geom);
CREATE INDEX parcels_neighborhood_idx ON parcels (neighborhood);

-- DOB NOW + DOB legacy, unified. Many rows per BBL.
CREATE TABLE permits (
  id              BIGSERIAL PRIMARY KEY,
  source          TEXT NOT NULL,          -- 'dob_now' | 'dob_legacy'
  external_id     TEXT NOT NULL,          -- see §4 for per-source derivation
  bbl             CHAR(10) REFERENCES parcels(bbl),   -- NULL when study_area_match='spatial'
  neighborhood    TEXT REFERENCES study_areas(name) ON UPDATE CASCADE,
  study_area_match TEXT NOT NULL                       -- 'bbl' | 'spatial' (D7)
    CHECK (study_area_match IN ('bbl', 'spatial')),
  bin             TEXT,
  address         TEXT,
  filing_number   TEXT,
  permit_type     TEXT,                   -- raw source value
  work_type       TEXT,                   -- raw source value
  category        TEXT NOT NULL,          -- canonical: new_building|alteration|demolition|other
  filing_reason   TEXT,
  status          TEXT,
  description     TEXT,
  estimated_cost  NUMERIC(14,2),          -- parsed from text (Risk R5)
  approved_date   DATE,
  issued_date     DATE,
  expired_date    DATE,
  event_date      DATE NOT NULL,          -- the date the feed sorts on; see note below
  latitude        DOUBLE PRECISION,
  longitude       DOUBLE PRECISION,
  geom            GEOMETRY(Point, 4326),
  owner_name      TEXT,
  raw             JSONB,                  -- source record as received
  retrieved_at    TIMESTAMPTZ NOT NULL,
  CONSTRAINT permits_natural_key UNIQUE (source, external_id)
);
CREATE INDEX permits_bbl_idx        ON permits (bbl);
CREATE INDEX permits_neighborhood_idx ON permits (neighborhood);
CREATE INDEX permits_event_date_idx ON permits (event_date DESC);
CREATE INDEX permits_category_idx   ON permits (category);
CREATE INDEX permits_geom_idx       ON permits USING GIST (geom);
CREATE INDEX permits_feed_idx       ON permits (event_date DESC, category, estimated_cost);

-- ACRIS documents. Many rows per BBL.
CREATE TABLE property_records (
  id             BIGSERIAL PRIMARY KEY,
  source         TEXT NOT NULL DEFAULT 'acris',
  external_id    TEXT NOT NULL,           -- document_id + block/lot (one doc spans lots)
  document_id    TEXT NOT NULL,
  bbl            CHAR(10) REFERENCES parcels(bbl),
  bbl_confidence TEXT NOT NULL,           -- 'exact' | 'condo_rollup' | 'unmatched' (Risk R4)
  document_type  TEXT NOT NULL,           -- DEED, MTGE, ...
  document_label TEXT,                    -- resolved via ACRIS doc control codes
  property_type  TEXT,
  recorded_date  DATE,
  document_date  DATE,
  amount         NUMERIC(16,2),
  parties        JSONB,                   -- [{name, type}]
  raw            JSONB,
  retrieved_at   TIMESTAMPTZ NOT NULL,
  CONSTRAINT property_records_natural_key UNIQUE (source, external_id)
);
CREATE INDEX property_records_bbl_idx  ON property_records (bbl);
CREATE INDEX property_records_date_idx ON property_records (recorded_date DESC);

-- Neighborhood-level ACS. Keyed by geography, never by BBL (PRD §6).
CREATE TABLE census_context (
  geography_id   TEXT NOT NULL,           -- census tract GEOID
  geography_type TEXT NOT NULL DEFAULT 'tract',
  tract_vintage  SMALLINT NOT NULL,       -- 2010 or 2020; boundaries differ (Risk R11)
  year           SMALLINT NOT NULL,       -- ACS5 vintage: 2014 | 2019 | 2024
  variable       TEXT NOT NULL,           -- e.g. 'B19013_001E'
  variable_label TEXT,
  value          NUMERIC,
  margin_of_error NUMERIC,
  retrieved_at   TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (geography_id, tract_vintage, year, variable)
);

-- Audit log: one row per pipeline execution, success or failure (PRD §10, §14).
CREATE TABLE ingestion_runs (
  id               BIGSERIAL PRIMARY KEY,
  source           TEXT NOT NULL,
  started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at     TIMESTAMPTZ,
  cursor_start     TEXT,                  -- incremental watermark used
  cursor_end       TEXT,                  -- watermark to resume from next run
  records_received INTEGER NOT NULL DEFAULT 0,
  records_inserted INTEGER NOT NULL DEFAULT 0,
  records_updated  INTEGER NOT NULL DEFAULT 0,
  records_rejected INTEGER NOT NULL DEFAULT 0,
  status           TEXT NOT NULL,         -- 'running' | 'success' | 'failed'
  error_message    TEXT
);
CREATE INDEX ingestion_runs_source_idx ON ingestion_runs (source, started_at DESC);

-- Records that failed validation. Logged, never silently dropped (PRD §14).
CREATE TABLE rejected_records (
  id          BIGSERIAL PRIMARY KEY,
  run_id      BIGINT REFERENCES ingestion_runs(id),
  source      TEXT NOT NULL,
  reason      TEXT NOT NULL,
  raw         JSONB NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Design notes**

- `event_date` exists because the feed is chronological across heterogeneous sources (PRD §7A). DOB NOW uses `issued_date`, falling back to `approved_date`; legacy uses `issuance_date`; ACRIS uses `recorded_date`. Without one canonical sort column, every feed query becomes a `COALESCE` over source-specific columns.
- `category` is the canonical new building / alteration / demolition classification the map colors by (PRD §7B). DOB NOW `work_type` and legacy `job_type` (A1/A2/A3/NB/DM) map into it in the adapters. Raw values are preserved alongside.
- `raw JSONB` preserves the source record so a mapping bug is fixable by reprocessing rather than refetching.
- `bbl_confidence` on `property_records` records *how* a document was attached to a parcel, so the methodology page and UI can be honest about condo rollups (Risk R4).
- `UNIQUE (source, external_id)` on both fact tables is the idempotency mechanism — all writes go through `INSERT ... ON CONFLICT (source, external_id) DO UPDATE`.
- The `permits.bbl` FK to `parcels` implies PLUTO loads first (M3 before M4). Permits whose BBL is absent from PLUTO are held in `rejected_records` rather than dropped.

### Additions beyond PRD §10

The PRD's suggested schema is a starting point; six deliberate additions: `raw` (reprocessing without refetch), `category` (the map needs one canonical classification), `event_date` (cross-source chronological sort), `bbl_confidence` (honest condo joins), `rejected_records` + cursor columns on `ingestion_runs` (PRD §14's "log malformed records" and incremental resume both need somewhere to live), `study_area_bbls` (the materialized point-in-polygon result every adapter's study-area filter reads from, added in M1), and — from the post-M3 audit — `study_area_bbls.resolution_method` plus `permits.study_area_match`/`permits.neighborhood`, which make decisions D6 and D7 legible in the data rather than implicit in the loader.

---

## 4. Data-source boundaries

One adapter per source (PRD §8). Each owns exactly one dataset's quirks and emits canonical rows. Verified contracts:

| Source | Dataset | Cursor (incremental) | Natural key | BBL strategy |
|---|---|---|---|---|
| DOB NOW | `rbx6-tga4` | `approved_date` (`calendar_date`) | `job_filing_number` + `work_permit` + `sequence_number` + `work_type` + `tracking_number` (see R1) | `bbl` field, numeric → zero-pad to 10 |
| DOB legacy | `ipu4-2q9a` | `dobrundate` (`calendar_date`) | `permit_si_no` | `bbl` field; fallback boro-name→code + padded block/lot |
| PLUTO | `64uk-42ks` (pinned `26v2`) | none — versioned snapshot, full reload | `bbl` | `bbl` is float-formatted text; truncate decimal |
| ACRIS | `bnx9-e6tj` (master), `8h5j-fqxa` (legals), `636b-3b5g` (parties), `7isb-wh4c` (codes) | `modified_date` on master | `document_id` + block + lot | from **legals** only; master has no BBL |
| Census ACS | `api.census.gov/data/{2014,2019,2024}/acs/acs5` | fixed vintage set | GEOID + tract vintage + year + variable | none — tract-level, never parcel-level |

**Per-source rules**

- **DOB NOW** — the primary source; build it first and most carefully. `estimated_job_costs` is `text`, not numeric. `bbl` is `number`, so it must be integer-cast before string conversion or it arrives as `1.012730012E9`. Filter server-side with `$where` on the study-area BBL set, batched (URL length limits force chunking of large `IN` lists).
- **DOB legacy** — the historical record for everything before DOB NOW's 2016-06-14 start. **Backfill scope: all available history** (decision D2). Manhattan-wide this is 1.62M rows, but the study area is ~1–2% of Manhattan, so the realistic load is ~20–30k rows — cheap enough that a full baseline beats an arbitrary cutoff for longitudinal work. Its date fields are `text` in `MM/DD/YYYY` format, so server-side date range filtering is impossible; `dobrundate` is the only real cursor. Parse dates in the adapter, never in SQL. Run as a one-time backfill, then daily incremental on `dobrundate`.
- **PLUTO** — a periodic versioned republication, not a stream. Treat as full reload into a staging table, then swap; record `pluto_version`. **Pinned to `26v2`** (the only currently published version); version bumps are a deliberate manual step, never automatic, so a new release cannot silently move parcel attributes mid-research (decision D3).
- **ACRIS** — a normalized multi-table system, unavoidably a two-stage fetch: query **legals** by study-area borough/block/lot to get `document_id`s, then fetch **master** for those IDs. Never scan master directly (4.2M mortgages, 3.6M deeds citywide). **V1 document set (decision D4): conveyances `DEED`, `DEEDO`, `CORRD`; mortgage lifecycle `MTGE`, `ASST`, `SAT`.** Conveyances answer who is buying and selling; the mortgage lifecycle often signals a redevelopment plan before any permit is filed. Lease types (`LEAS`, `AL&R`) and transfer-tax filings (`RPTT`) are excluded from V1 — uneven coverage and duplicate-looking feed events respectively. `doc_type` codes resolve to labels via `7isb-wh4c`, where the field is `doc__type` / `doc__type_description` (double underscore).
- **Census** — tract-level only. The `census_context` table has no BBL column by design and must not acquire one; PRD §6 is explicit that Census data stays neighborhood-level and secondary. **Vintages: ACS5 2014, 2019, 2024** (decision D5) — spaced 5 years apart so the samples do not overlap and the comparison is statistically legitimate. Note the tract-boundary discontinuity in Risk R11.

**Shared transforms** (`pipeline/transforms/`) — `bbl.py` is the highest-leverage module in the codebase, since all four property sources format BBL differently:

| Source | Raw form | Normalized |
|---|---|---|
| DOB NOW | `1012730012` (number) | `"1012730012"` |
| PLUTO | `"1002000001.00000000"` | `"1002000001"` |
| DOB legacy | `borough="MANHATTAN"`, `block="01413"`, `lot="00001"` | `"1014130001"` |
| ACRIS legals | `borough="1"`, `block="200"`, `lot="6"` | `"1002000006"` |

---

## 5. Major technical risks

Ordered by expected cost. R1–R5 are confirmed present in the live data, not hypothetical.

### R1 — DOB NOW's filing number is not a reliable key *(confirmed, high)*
315 records citywide have the literal string `"Permit is no"` in `job_filing_number` (with `work_permit` = `"Permit is not yet issued"`), and 212 more have it null. The field is truncated sentinel text for approved-but-unissued permits, not an identifier. Keying on it alone would collapse hundreds of distinct permits into one row and silently destroy data.

**Measured against the study area (audit, post-M3).** The composite key originally proposed here — `job_filing_number` + `work_permit` + `sequence_number` — is *itself* insufficient, and would have caused exactly the failure this risk was written to prevent. Across the 22,960 DOB NOW permits in the study-area bounding box:

| Key | Distinct keys | Colliding keys | Records merged | Collisions losing real data |
|---|---|---|---|---|
| `filing` + `work_permit` + `sequence` (as originally planned) | 21,033 | 1,772 | 1,927 | **1,771** |
| + `work_type` | 22,949 | 11 | 11 | 10 |
| + `work_type` + `filing_reason` | 22,954 | 6 | 6 | 5 |
| **+ `work_type` + `tracking_number`** | 22,957 | 3 | 3 | **0** |

These are not duplicate rows — only **one** byte-identical duplicate exists in the whole set. The collisions are genuinely distinct permits: one filing/permit/sequence triple carries both a `'Supported Scaffold'` and a `'Sidewalk Shed'` permit, and the collisions remaining after adding `work_type` are **permit renewals** — same filing and work type, different `issued_date`/`expired_date`, separated only by `tracking_number`. The three residual collisions under the full key lose no data (identical rows), which is precisely what an idempotent upsert should collapse.

*Mitigation:* external ID = `job_filing_number` + `work_permit` + `sequence_number` + `work_type` + `tracking_number`; when any component is a sentinel or null, fall back to a stable hash of `(bbl, work_type, approved_date, job_description)` — the `"Permit is no"` sentinel rows were confirmed to carry *differing* BBL/BIN/lat-long, so they are distinct permits needing the hash, not duplicates. `tracking_number` was non-null on all 22,960 study-area records. Assert in tests that the study-area external-ID count equals the count of *distinct records* (not of raw records — source-level exact duplicates legitimately collapse). Route unresolvable records to `rejected_records`.

**This also constrains the upsert mechanics.** `ON CONFLICT DO UPDATE` raises `CardinalityViolation` ("cannot affect row a second time") when one batch contains two rows sharing a conflict key — verified directly against Postgres. So M4 must dedupe by external ID in Python before upserting, exactly as `pipeline/sources/pluto.py` keys by BBL. Under the *wrong* key that dedupe silently discards 1,927 real permits instead of erroring, which is why the key above must land before M4's loader is written.

### R2 — Missing BBLs on ~0.6% of permits *(confirmed, medium)*
320 of 54,346 Manhattan DOB NOW records have a null BBL. The FK to `parcels` will reject them, and they are exactly the records most likely to be interesting (new construction on irregular lots).

*Mitigation:* address-based fallback resolution against PLUTO (`house_no` + `street_name`), only when BBL is genuinely absent (PRD §9). Record the resolution method. Anything unresolved goes to `rejected_records` and is reported in the run summary — never dropped.

### R3 — BBL format divergence across sources *(confirmed, medium)*
PLUTO returns `"1002000001.00000000"`; DOB NOW returns a JSON *number*; legacy returns zero-padded block/lot with a borough *name*; ACRIS returns a borough digit with unpadded block/lot. A naive join across these produces zero matches, and — worse — a partially correct one produces a *plausible but wrong* match rate that is easy to miss.

*Mitigation:* one `normalize_bbl()` used by every adapter; `CHAR(10)` column type; property-based tests covering all four input shapes; a post-ingestion check asserting join rate against `parcels` exceeds a threshold and failing the run if it drops.

### R4 — ACRIS condo unit lots do not exist in PLUTO *(confirmed, medium-high)*
On Manhattan block 200, ACRIS legals carry lots 1117–1121 and 6400 (condo unit lots), while PLUTO has lots 1, 17, 22, 24. Condo transactions therefore have no matching parcel row and would either violate the FK or vanish. This affects precisely the buildings with the most transaction activity.

*Mitigation:* detect unit lots (≥1001) and roll them up to the base/billing lot, recording `bbl_confidence = 'condo_rollup'`; leave genuinely unmatched documents attached at block level with `'unmatched'`. Surface the distinction in the UI and on `/methodology`. Deep condo-declaration parsing is explicitly out of V1 scope (PRD §17) — the goal is honesty about the limitation, not resolution of it.

### R5 — Cost and date fields are text *(confirmed, low-medium)*
`estimated_job_costs` is `text` in DOB NOW; every legacy date field is `text` in `MM/DD/YYYY`. Cost-based filtering and sorting (PRD §7A) depend on clean numerics.

*Mitigation:* `transforms/money.py` and `transforms/dates.py` handle parsing; unparseable values become NULL with a `rejected_records` note rather than a guessed zero — a zero would corrupt the digest's total-cost aggregate (PRD §7E).

### R6 — Study-area boundary is a research artifact, not ground truth *(design, medium)*
Boundaries are researcher-drawn (PRD §5). If they are implicit in query filters, the study area becomes unreproducible and the thesis loses defensibility.

*Mitigation:* boundary lives in `study_areas` as versioned geometry with a `definition_note`, is the sole input to the derived BBL set, and is stated plainly on `/methodology` and in the UI. Never hardcode block lists in queries.

### R7 — Serverless Postgres connection exhaustion *(operational, medium)*
FastAPI on Vercel functions means many short-lived instances; direct Postgres connections will exhaust Supabase's limit under even light concurrent load.

*Mitigation:* connect through Supabase's transaction pooler (port 6543), not the direct port; small per-instance pool sizes; no long-lived transactions in request handlers. The ingestion job — a single long-lived process — uses the direct connection instead.

### R8 — Silent ingestion failure *(operational, medium)*
A cron job that fails quietly is worse than no cron job: the tool shows stale data while appearing healthy, and a thesis conclusion could rest on a feed that stopped updating weeks ago.

*Mitigation:* every run writes an `ingestion_runs` row before work begins and updates it in a `finally` block; non-zero exit on any failure so GitHub Actions surfaces it (PRD §13); the UI displays last-successful-run time per source; a run that receives zero records where records were expected is treated as suspicious, not successful.

### R9 — Socrata rate limits and paging drift *(external, low-medium)*
Volumes are modest (54k Manhattan DOB NOW rows; ~3.4k study-area parcels), so limits are unlikely to bite — but `$offset` paging over a dataset being written concurrently can skip or duplicate rows.

*Mitigation:* app token on every request; retry with exponential backoff on 429/5xx; always page with an explicit `$order` on a stable key so pagination is deterministic; rely on upsert to absorb any duplicates that slip through.

### R10 — Upstream schema drift *(external, low)*
Socrata dataset IDs and column names change between publication versions — PLUTO especially, as each release is effectively a new dataset.

*Mitigation:* the adapter-per-source structure contains the blast radius (PRD §8); validate expected columns at fetch time and fail loudly with a named missing column rather than producing rows full of nulls; pin dataset IDs in config, not scattered through code.

### R11 — Census tract boundaries change between ACS vintages *(confirmed, medium)*
The chosen vintages straddle a decennial geography change: ACS5 2014 and 2019 are published on **2010** census tracts, while ACS5 2024 uses **2020** tracts. Tracts were split, merged, and renumbered between them. Joining all three on a single `census_tract` column would silently compare different pieces of ground and manufacture apparent demographic "change" that is purely an artifact of redistricting — a serious hazard for a thesis making longitudinal claims.

*Mitigation:* PLUTO carries both `ct2010` and `bct2020`, so parcels are tagged with both vintages and each ACS year joins on the matching one (see `parcels` and `census_context` in §3). `census_context.tract_vintage` is part of the primary key, making a cross-vintage join impossible to write by accident. The methodology page states plainly that pre-2020 and post-2020 tract figures are not strictly comparable.

---


### R12 — The BBL allowlist under-covers the study area *(confirmed, medium-high)*
The study-area filter is a BBL allowlist derived from PLUTO **centroids**, so a lot with no centroid, no PLUTO row, or a condo unit-lot BBL cannot enter it — and every permit on such a lot is then dropped at the study-area filter stage, silently and without a `rejected_records` entry.

Measured (audit, post-M3): of the 8,721 DOB NOW permits falling spatially inside the study-area polygons, **272 (3.1%) would be dropped** by the BBL filter — 73 with a null BBL (R2), 54 on condo unit lots (R4, which affects DOB and not only ACRIS), and 145 on lots absent from `parcels`. Two distinct causes:

- **Centroid-less PLUTO lots.** 398 Manhattan lots have no lat/long, and `resolve.py` filters `latitude IS NOT NULL`, so they can never be resolved into any study area. **10 sit on study-area blocks**, including `1003540001` and `1003520001` (ESSEX STREET — the Essex Crossing footprint), `1003419001`/`1003419058`/`1003419070` (GRAND STREET), and `1002791108` (11 EAST BROADWAY, a Two Bridges condo unit lot). These skew heavily toward air-rights (`9xxx`) and condo lots — disproportionately the parcels where the largest development happens.
- **Lots absent from PLUTO entirely.** 7 distinct in-polygon BBLs carry permits but have no `parcels` row at all — merged or demapped lots. Since lot mergers are a signature of redevelopment, this bias grows worse the further back the legacy backfill reaches.

Verified clean in the same audit: **zero** reverse-gap (no allowlisted BBL falls outside the polygons), **zero** FK violations against the current `parcels`, and **zero** unparseable BBLs across all 22,960 records.

*Mitigation (decisions D6(b) and D7(b), §6).* Both causes are addressed, and both are stated on `/methodology`, since together they define what "in the study area" means for every number the thesis reports.

- **D6(b), implemented.** `resolve.py` admits centroid-less lots by unambiguous block membership. All 10 study-area lots were admitted with zero ambiguous blocks, taking the allowlist from 1,944 to **1,954** BBLs; the Essex Crossing parcels and the Two Bridges condo lot now carry `parcels` rows. Re-measured, this alone closes 21 of the 272 dropped permits (272 → 251).
- **D7(b), schema landed, adapter pending in M4.** `permits.study_area_match` and `permits.neighborhood` (migration `0012`) let M4 keep the remaining 251 in-polygon permits — the null-BBL, condo-lot, and merged-lot cases that no BBL allowlist can reach. Precedence for M4 to implement: try the BBL allowlist first (`study_area_match = 'bbl'`); otherwise, if the permit's own point falls inside a study-area polygon, keep it with `study_area_match = 'spatial'`, a null `bbl` (its BBL has no `parcels` row, so the FK cannot hold it), and the neighborhood taken from the containing polygon.

A residual limitation stands and belongs on `/methodology`: a spatially-matched permit appears in the feed and on the map but cannot appear on any parcel page, because there is no parcel to attach it to.

---

## 6. Decisions

Resolved 2026-08-31. Nothing here blocks implementation.

| # | Decision | Resolution |
|---|---|---|
| D1 | Study-area geometry | NTA 2020 as base; `Chinatown-Two Bridges` hand-split into two areas, `Lower East Side` taken as-is → **3 study areas**. Split line documented in `study_areas.definition_note` and on `/methodology`. |
| D2 | Legacy permit depth | **All available history.** ~20–30k study-area rows expected; one-time backfill, then `dobrundate` incremental. |
| D3 | PLUTO version | Pin **`26v2`** (only published version). Version bumps are a deliberate manual step, never automatic. |
| D4 | ACRIS document types | **`DEED`, `DEEDO`, `CORRD`** (conveyances) + **`MTGE`, `ASST`, `SAT`** (mortgage lifecycle). Leases and RPTT excluded from V1. |
| D5 | ACS vintages | **ACS5 2014, 2019, 2024** — 5-year spacing, non-overlapping samples. Tract-vintage handling per Risk R11. |
| D6 | Centroid-less study-area lots | **Admit by block membership.** A PLUTO lot with no centroid joins the study area when its block unambiguously belongs to one; a block straddling two areas leaves the lot unresolved rather than assigned by majority. Recorded per row in `study_area_bbls.resolution_method` (`'centroid'` \| `'block_membership'`) and surfaced on `/methodology`, since block membership is a weaker claim than point-in-polygon. |
| D7 | Permit study-area filter | **BBL ∪ point-in-polygon.** A permit enters the study area either because its BBL is in the allowlist or because its own point falls inside a study-area polygon. `permits.study_area_match` (`'bbl'` \| `'spatial'`) records which, and `permits.neighborhood` is carried on the row because a spatial match has no `parcels` row to join through. |

### Still to specify (during the milestone that needs it, not before)

- **ACS variable list** — pinned during M8. PRD §6 names the candidates (median household income, median gross rent, population, tenure); the specific ACS5 table codes get fixed then, since only the Census adapter depends on them.

### Resolved during M1

- **The Chinatown / Two Bridges split line** — settled on the Division Street centerline rather than the Bowery/St James Place corridor originally floated here. Division St is the conventional dividing line in local usage and is available as clean, mergeable centerline geometry from NYC DOT's LION dataset, which made it both more defensible and more reproducible than a hand-drawn approximation. See the M1 section above.

---

## Appendix A — Verified source reconnaissance

Checked live against `data.cityofnewyork.us` on 2026-08-31. All seven dataset IDs returned HTTP 200.

| Dataset | ID | Verified name |
|---|---|---|
| DOB NOW: Build – Approved Permits | `rbx6-tga4` | DOB NOW: Build – Approved Permits |
| DOB Permit Issuance (legacy) | `ipu4-2q9a` | DOB Permit Issuance |
| PLUTO | `64uk-42ks` | Primary Land Use Tax Lot Output (PLUTO) |
| ACRIS Real Property Master | `bnx9-e6tj` | ACRIS - Real Property Master |
| ACRIS Real Property Legals | `8h5j-fqxa` | ACRIS - Real Property Legals |
| ACRIS Real Property Parties | `636b-3b5g` | ACRIS - Real Property Parties |
| ACRIS Document Control Codes | `7isb-wh4c` | ACRIS - Document Control Codes |

**Volumes** — DOB NOW Manhattan: 54,346 records. DOB legacy Manhattan: 1,624,467 records. PLUTO citywide: 858,284 lots (version `26v2`, the only published version); Manhattan blocks 100–400: 3,412 lots. ACRIS master citywide: 4.22M `MTGE`, 3.65M `DEED`, 2.63M `SAT`.

**Temporal coverage** — DOB NOW `approved_date` spans **2016-06-14 → 2026-08-28**; everything earlier requires the legacy dataset. Legacy Manhattan permits by issuance year: 1990 → 12,000; 2000 → 44,623; 2010 → 58,442; 2015 → 78,794; 2020 → 32,574; 2023 → 6,208 — the taper after 2020 reflects DOB NOW taking over, confirming the two sources are sequential rather than parallel.

**Geography** — NTA 2020 provides `Chinatown-Two Bridges` (910 Manhattan DOB NOW permits) and `Lower East Side` (734) as distinct neighborhoods. Chinatown and Two Bridges are *combined* in official NTA geography, which is why D1 requires a hand split. PLUTO exposes both `ct2010` and `bct2020`, enabling the dual tract-vintage join in Risk R11.

**Census** — ACS5 vintages available: 2009 through 2024 continuously. Selected: 2014, 2019, 2024.

**ACRIS document codes** (`7isb-wh4c`, fields `doc__type` / `doc__type_description`) — selected for V1: `DEED` (Deed), `DEEDO` (Deed, Other), `CORRD` (Correction Deed) in class *Deeds and Other Conveyances*; `MTGE` (Mortgage), `ASST` (Assignment, Mortgage), `SAT` (Satisfaction of Mortgage) in class *Mortgages & Instruments*. Considered and excluded: `LEAS`, `AL&R`, `RPTT`, `RPTT&RET`.

**Field-level findings**

- DOB NOW `approved_date` / `issued_date` / `expired_date` are proper `calendar_date` types — usable as server-side incremental cursors. Manhattan nulls: `approved_date` 1, `issued_date` 9. `approved_date` is the better watermark.
- DOB NOW `estimated_job_costs` is `text`; `bbl` and `census_tract` are `number`.
- DOB legacy exposes only `dobrundate` as a `calendar_date`; `filing_date`, `issuance_date`, `expiration_date`, `job_start_date` are all `text` in `MM/DD/YYYY`.
- PLUTO `bbl` serializes as `"1002000001.00000000"`. Census tract field is `bct2020`.
- ACRIS master carries `modified_date` (usable cursor) but no BBL; legals carries borough/block/lot but no dates or amounts. The two must be joined on `document_id`.
- ACRIS legals on Manhattan block 200 shows condo unit lots (1117–1121, 6400) absent from PLUTO's lot set (1, 17, 22, 24) — the basis of Risk R4.

Reconnaissance commands are reproducible against the Socrata `$select`/`$where`/`$group` API; no app token was required for these metadata reads, though one should be sent on all production requests.
