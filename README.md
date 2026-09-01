# Lower Manhattan Development Tracker (Division)

Lower Manhattan Development Tracker began as a research tool for studying neighborhood change in Chinatown and Two Bridges. NYC development information is spread across several independently structured public datasets, making repeated parcel-level research cumbersome. The project combines permitting, land-use, property, and demographic records into a single research interface and automatically monitors new development activity.

Deployed as **Division**, named for Division Street -- the street decision D1 uses as the boundary hand-splitting the official `Chinatown-Two Bridges` NTA into the two separate study areas this tool tracks (see `IMPLEMENTATION_PLAN.md` §6 and `/methodology`). Hosted at `nicklam.co/division`.

**Status:** M0 (foundation), M1 (study-area definition), M2 (schema and migrations), M3 (PLUTO ingestion), M4 (DOB NOW ingestion), M5 (read API), and M6 (frontend) complete, plus a post-M3 data-integrity audit. The study area resolves to 1,954 parcels across the three neighborhoods, carrying 10,364 DOB NOW permits, served through a FastAPI read layer (`api/`) and a Next.js frontend (`web/`) -- feed, map, parcel pages, watchlist, and methodology. See `IMPLEMENTATION_PLAN.md` for the full build plan and milestone sequence.

## Documents

- [`PRD.md`](./PRD.md) — full product spec: scope, data sources, UX, data model.
- [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md) — architecture, milestones, database design, source boundaries, and technical risks.
- [`CLAUDE.md`](./CLAUDE.md) — guidance for AI coding agents working in this repo.

## Architecture

Two independent halves, connected only by the database:

- **`pipeline/`** — Python ingestion. Scheduled daily via GitHub Actions. One adapter per external source (DOB NOW, DOB legacy, PLUTO, ACRIS, Census), fetching, validating, normalizing, and upserting into Postgres.
- **`api/`** — FastAPI, read-only views over the ingested data.
- **`web/`** — Next.js + TypeScript frontend (feed, map, parcel pages, watchlist, methodology), deployed on Vercel.

The frontend never calls upstream APIs (Socrata, Census) directly — everything goes through the ingested Postgres data.

## Data sources

DOB NOW (current permits), historical DOB permit issuance, PLUTO (parcel context), ACRIS (recorded property documents), and Census ACS (neighborhood demographic context). See `IMPLEMENTATION_PLAN.md` §4 for per-source adapter contracts, and the `/methodology` page (once built) for how they're joined and what their limitations are.

## Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- A Supabase project (Postgres + PostGIS)
- A Socrata app token ([register here](https://data.cityofnewyork.us/profile/edit/developer_settings))
- A Census API key ([register here](https://api.census.gov/data/key_signup.html))

### Backend / pipeline

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # fill in SOCRATA_APP_TOKEN, CENSUS_API_KEY, SUPABASE_DB_URL_DIRECT, SUPABASE_DB_URL_POOLED

python scripts/check_db.py   # verify Supabase connectivity
python scripts/migrate.py    # apply pending SQL migrations from db/migrations/

python -m pipeline.study_area.load_boundaries   # load study areas into Postgres
python -m pipeline.study_area.resolve           # derive the study-area BBL set (needs SOCRATA_APP_TOKEN)

python -m pipeline.run --source pluto           # load study-area parcels from PLUTO
python -m pipeline.run --source dob_now         # load study-area permits from DOB NOW

uvicorn api.main:app --reload   # run the read API at http://localhost:8000 (docs at /docs)

pytest                       # run tests
ruff check .                 # lint
```

### Frontend

```bash
cd web
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL, defaults to http://localhost:8000
npm run dev     # http://localhost:3000/division (basePath -- see next.config.ts) -- run `uvicorn api.main:app --reload` alongside it
npm run build   # production build
npm run lint
```

## Deployment

Two separate Vercel projects, not one -- `api/`'s internal imports (`from api.db import ...`) need the repo root as their deployment root, which doesn't line up with Vercel's single-project convention for a Next.js app plus Python functions sharing one root directory. Splitting them also matches CLAUDE.md's architecture, which already treats `api/` and `web/` as independent halves.

**Both projects deploy via explicit CLI runs only -- neither has GitHub auto-deploy connected.** `division` had it briefly (a default of `vercel link --yes`, easy to miss) and it broke production: a git-triggered deploy always builds from the repo root, so an unrelated push silently redeployed `division` using the *repo-root* `vercel.json` -- the Python API's config, not the Next.js app's. See `IMPLEMENTATION_PLAN.md`'s M7 section for the full incident. To redeploy after a change:

```bash
cd web && vercel deploy --prod --yes       # division
cd .. && vercel deploy --prod --yes        # division-api (must run from repo root)
```

- **`division`** (`web/`) -- the Next.js frontend. Deployed with `web/` as the Vercel project's root directory. **Live:** https://division-theta.vercel.app. `next.config.ts` sets `basePath: "/division"`, since it's hosted at `nicklam.co/division` rather than its own subdomain. `NEXT_PUBLIC_API_URL` is set to `division-api`'s production URL.
- **`division-api`** (`api/`) -- the FastAPI backend. Deployed with the *repo root* as the Vercel project's root directory (not `api/`), via the root-level `vercel.json` and `requirements.txt` -- so `api/`'s absolute imports resolve exactly as they do locally, with zero code changes for deployment. **Live:** https://division-api-one.vercel.app. `SUPABASE_DB_URL_POOLED` (Risk R7) and `CORS_ALLOWED_ORIGINS` are set as environment variables; the latter is comma-separated and currently `http://localhost:3000,https://division-theta.vercel.app,https://nicklam.co,https://www.nicklam.co` -- `nicklam.co` (no `www`) 308-redirects to `www.nicklam.co`, so the `www` origin is the one that actually matters for a browser landing on `nicklam.co/division`, but both are allowed.

nicklam.co itself is a separate, already-live Vercel project (`my-site`), not part of this repo -- not touched here. `nicklam.co/division` is served via a rewrite added to that project's own `vercel.json`:

```json
{
  "rewrites": [
    { "source": "/division/:path*", "destination": "https://division-theta.vercel.app/division/:path*" }
  ]
}
```

Scheduled ingestion is separate from both: `.github/workflows/ingest.yml` runs `pluto` then `dob_now` daily via GitHub Actions (PRD §13), using repo secrets `SOCRATA_APP_TOKEN` and `SUPABASE_DB_URL_DIRECT` (the direct connection, not the pooler -- ingestion is a long-lived process, see Risk R7). A failed adapter run exits non-zero and fails the workflow visibly rather than swallowing the error.

## Limitations

Study-area boundaries (Chinatown, Two Bridges, adjacent Lower East Side) are researcher-defined, not official administrative geography — see `/methodology` and `IMPLEMENTATION_PLAN.md` §6 (decision D1) for how they were drawn. Which parcels fall inside those boundaries is also a judgment: most are resolved by point-in-polygon against parcel centroids, while lots PLUTO gives no centroid for are admitted by block membership, a weaker claim recorded per row (decision D6). The same is true of permits: most are matched to the study area by their parcel's BBL, but 279 of 10,364 have no BBL the allowlist can reach (a null BBL, a condo unit lot, or a merged/demapped lot) and are matched instead by their own point falling inside a study-area polygon (decision D7) — such a permit carries a null `bbl` and appears in the feed and on the map, but not on any parcel page or `/api/parcels/{bbl}/permits` response, since there is no parcel for it to be a sub-resource of. `GET /api/parcels/{bbl}/records` and `/api/stats`'s digest windows are scoped to `permits` only and will return no ACRIS activity until M8 loads `property_records`. The watchlist can bookmark a parcel or a block with a real activity feed behind each, but a free-text address bookmark is a note only — there's no address-to-BBL matching (a deliberate scope decision, not an oversight; see R2 and the M6 section). The map's basemap is OpenFreeMap's free "Positron" style, a default pending a deliberate basemap/tile-provider decision. Other known data-quality caveats (BBL format divergence, ACRIS condo-lot matching, census tract vintage discontinuities) are documented in `IMPLEMENTATION_PLAN.md` §5.
