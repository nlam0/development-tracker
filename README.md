# Lower Manhattan Development Tracker

Lower Manhattan Development Tracker began as a research tool for studying neighborhood change in Chinatown and Two Bridges. NYC development information is spread across several independently structured public datasets, making repeated parcel-level research cumbersome. The project combines permitting, land-use, property, and demographic records into a single research interface and automatically monitors new development activity.

**Status:** M0 (foundation), M1 (study-area definition), M2 (schema and migrations), and M3 (PLUTO ingestion) complete, plus a post-M3 data-integrity audit. The study area resolves to 1,954 parcels across the three neighborhoods. See `IMPLEMENTATION_PLAN.md` for the full build plan and milestone sequence.

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

cp .env.example .env   # fill in SOCRATA_APP_TOKEN, CENSUS_API_KEY, SUPABASE_DB_URL_*

python scripts/check_db.py   # verify Supabase connectivity
python scripts/migrate.py    # apply pending SQL migrations from db/migrations/

python -m pipeline.study_area.load_boundaries   # load study areas into Postgres
python -m pipeline.study_area.resolve           # derive the study-area BBL set (needs SOCRATA_APP_TOKEN)

python -m pipeline.run --source pluto           # load study-area parcels from PLUTO

pytest                       # run tests
ruff check .                 # lint
```

### Frontend

```bash
cd web
npm install
npm run dev     # http://localhost:3000
npm run build   # production build
npm run lint
```

## Limitations

Study-area boundaries (Chinatown, Two Bridges, adjacent Lower East Side) are researcher-defined, not official administrative geography — see `/methodology` (once built) and `IMPLEMENTATION_PLAN.md` §6 (decision D1) for how they were drawn. Which parcels fall inside those boundaries is also a judgment: most are resolved by point-in-polygon against parcel centroids, while lots PLUTO gives no centroid for are admitted by block membership, a weaker claim recorded per row (decision D6). Other known data-quality caveats (BBL format divergence, ACRIS condo-lot matching, census tract vintage discontinuities) are documented in `IMPLEMENTATION_PLAN.md` §5.
