# Lower Manhattan Development Tracker

## 1. Product Summary

A lightweight research tool for monitoring property development and permitting activity across Chinatown, Two Bridges, and adjacent Lower Manhattan neighborhoods.

The tool aggregates public NYC property and construction records into a single searchable interface, allowing a researcher to identify recent development activity, inspect individual parcels, and track changes over time without repeatedly searching several city databases.

The initial product was conceived as research infrastructure for a senior thesis on economic, commercial, and spatial change in Lower Manhattan.

## 2. Problem

Researching neighborhood development requires repeatedly moving among fragmented city datasets.

A researcher trying to understand what is changing at a particular property may need to separately inspect:

* building permits
* tax-lot characteristics
* property transactions
* zoning and land-use attributes
* demographic context

These datasets use different schemas, identifiers, and geographic units. The result is repetitive manual work and difficulty seeing development patterns across an entire neighborhood.

## 3. Product Goal

Create one interface that answers:

**What development activity is happening in my study area, where is it happening, and what do the underlying public records tell me about it?**

The product should make it possible to go from a neighborhood-level view to the history of an individual parcel in a few clicks.

## 4. Target User

Primary user:

**Urban researcher conducting longitudinal neighborhood research.**

Secondary users:

* students
* journalists
* planners
* neighborhood organizations
* civic researchers

V1 should optimize for a single serious researcher rather than attempt to become a general-purpose NYC real-estate platform.

## 5. Geographic Scope

V1 study areas:

* Chinatown
* Two Bridges
* Lower East Side immediately adjacent to the study area

Use explicit geographic boundaries stored in the application rather than attempting to cover all five boroughs.

The interface should clearly state that neighborhood boundaries are research definitions and may not correspond perfectly to official administrative boundaries.

## 6. Core Data Sources

### DOB NOW: Build — Approved Permits

Primary source for current construction-permit activity.

Capture fields including:

* BBL
* address
* latitude / longitude
* filing number
* work type
* filing reason
* issued / approved date
* estimated job cost
* job description
* owner
* permit status

### Historical DOB Permit Issuance

Use selectively for older permit records predating or outside DOB NOW coverage.

### PLUTO

Use for parcel-level context:

* BBL
* land use
* zoning
* lot area
* building area
* residential units
* commercial area
* year built
* number of buildings
* assessed value or other relevant property attributes
* latitude / longitude or geometry where available

### ACRIS

Use for recorded property activity.

V1 should focus on a limited set of document types useful to thesis research rather than attempting to interpret the entire ACRIS system.

Relevant outputs may include:

* transaction date
* document type
* recorded amount where applicable
* parties
* property identifiers

### Census ACS

Use only for neighborhood-level context, not individual parcel profiles.

Possible variables:

* median household income
* median gross rent
* population
* tenure
* selected demographic measures

Census data should remain secondary to the property and permitting workflow.

## 7. Core User Experience

### A. Development Feed

Default landing page.

Show a chronological feed of relevant activity in the study area.

Each event card should display:

**Address**
Permit / transaction type
Date
Estimated project cost where available
Short job description
Neighborhood
Source

Filters:

* neighborhood
* date range
* permit type
* estimated project cost
* new building / alteration / demolition
* source

Allow sorting by:

* newest
* oldest
* estimated cost

### B. Interactive Map

Display development events geographically.

Markers should represent properties with recent activity.

Map behavior:

* marker clustering at low zoom
* click marker to open property summary
* filters update both map and feed
* visually distinguish major categories such as new building, alteration, demolition, and property transaction
* study-area boundary visible on map

No elaborate 3D visualization.

### C. Parcel / Property Page

Each property receives a page keyed primarily by BBL.

Display:

**Property**

* address
* BBL
* land-use category
* zoning
* lot area
* building area
* year built
* residential units

**Recent Development**

* permits
* permit dates
* job descriptions
* estimated costs
* work types

**Property Activity**

* selected ACRIS records
* transaction/document dates
* recorded amounts where meaningful

**Context**

* neighborhood
* census tract
* link back to map

The objective is to make a parcel's recent development history understandable quickly.

### D. Watchlist

Allow a user to bookmark:

* individual parcels
* addresses
* blocks

A watchlist page shows activity across saved properties.

Authentication is not required for V1. Store the watchlist locally in the browser.

### E. Research Digest

Generate a simple summary:

**Development activity in the past 7 / 30 / 90 days**

Examples:

* number of new permits
* number of properties with activity
* total reported estimated job cost
* largest projects
* new building permits
* demolition permits
* blocks with multiple filings

Allow the user to copy or export the result.

V1 does not need generative AI.

## 8. Data Pipeline

The application should separate ingestion from the user-facing application.

### Ingestion

Python scripts query public APIs and retrieve records relevant to the geographic study area.

Pipeline:

1. Fetch
2. Validate
3. Normalize
4. Resolve BBL
5. Filter to study area
6. Deduplicate
7. Upsert into PostgreSQL
8. Record ingestion timestamp

Each source should have its own adapter so schema changes in one source do not affect the rest of the application.

Example structure:

```text
pipeline/
  sources/
    dob_now.py
    dob_legacy.py
    pluto.py
    acris.py
    census.py
  transforms/
    addresses.py
    bbl.py
    geography.py
  load.py
```

## 9. Canonical Identifiers

Use **BBL** as the main parcel identifier whenever available.

Normalize it consistently to a 10-digit string:

```text
borough + block + lot
```

Store external source IDs separately.

Do not rely on street address as the primary join key unless BBL is unavailable.

## 10. Database

Use PostgreSQL.

Suggested tables:

### parcels

* bbl
* address
* borough
* block
* lot
* neighborhood
* latitude
* longitude
* zoning
* land_use
* lot_area
* building_area
* year_built
* units_residential

### permits

* id
* source
* external_id
* bbl
* filing_number
* permit_type
* work_type
* status
* description
* estimated_cost
* approved_date
* issued_date
* retrieved_at

### property_records

* id
* source
* external_id
* bbl
* document_type
* recorded_date
* amount
* retrieved_at

### census_context

* geography_id
* year
* variable
* value

### ingestion_runs

* source
* started_at
* completed_at
* records_received
* records_inserted
* records_updated
* status
* error_message

## 11. Backend

Use **Python + FastAPI**.

Required endpoints:

```text
GET /api/activity
GET /api/parcels/{bbl}
GET /api/parcels/{bbl}/permits
GET /api/parcels/{bbl}/records
GET /api/map
GET /api/stats
```

Endpoints should support appropriate filtering and pagination.

## 12. Frontend

Use:

* React / Next.js
* TypeScript
* a lightweight component library or minimal custom CSS
* MapLibre GL JS for mapping

Visual direction should feel closer to a research instrument than a startup dashboard.

Prioritize:

* typography
* information density
* fast filtering
* restrained visual hierarchy
* map / list interaction

Avoid:

* gradients
* oversized cards
* excessive rounded UI
* AI aesthetic
* unnecessary animation

## 13. Scheduled Updates

V1 should run ingestion once per day.

A scheduled workflow should:

1. fetch records added or updated since the last successful run
2. normalize the records
3. upsert them
4. log results
5. fail visibly if ingestion breaks

A GitHub Actions scheduled job is sufficient for V1.

The application should never need to re-download the entire dataset during normal operation.

## 14. Reliability Requirements

The pipeline should:

* handle API timeouts
* retry transient failures
* avoid inserting duplicate records
* validate required identifiers
* log malformed records
* preserve raw source IDs
* make ingestion idempotent

Running the same ingestion job twice should not create duplicate data.

## 15. Methodology Page

Include a public `/methodology` page explaining:

* why the tool was built
* study geography
* data sources
* update frequency
* how datasets are joined
* known limitations
* definitions of major permit categories

This is important because the project originated as academic research.

It also demonstrates written communication and responsible handling of government data.

## 16. V1 Success Criteria

V1 is complete when:

* current DOB NOW permits can be ingested automatically
* PLUTO parcel context can be joined by BBL
* the application contains real records from Chinatown and Two Bridges
* users can browse development activity chronologically
* users can filter activity
* users can view activity on a map
* clicking a property exposes its permit and property information
* scheduled ingestion works reliably
* duplicate ingestion does not create duplicate records
* methodology and source information are documented
* the project is deployed publicly
* the repository has a clear README with setup instructions

## 17. Explicitly Out of Scope for V1

Do not build:

* user accounts
* payments
* social features
* mobile apps
* AI summaries
* automated zoning interpretation
* predictive development scores
* all-NYC coverage
* sophisticated property valuation models
* complicated ACRIS document interpretation
* real-time streaming infrastructure

Finish the basic research tool first.

## 18. V1.1 After Launch

Only after V1 works:

* saved searches
* weekly email digest
* CSV exports
* compare two time periods
* historical PLUTO snapshots
* additional ACRIS transaction analysis
* community-board or planning-hearing data
* user-created study areas
* automated alerts for watched parcels

## 19. README Story

The public README should explain the project approximately as follows:

> Lower Manhattan Development Tracker began as a research tool for studying neighborhood change in Chinatown and Two Bridges. NYC development information is spread across several independently structured public datasets, making repeated parcel-level research cumbersome. The project combines permitting, land-use, property, and demographic records into a single research interface and automatically monitors new development activity.

The README should then explain architecture, sources, methodology, setup, and limitations.

## 20. Infrastructure Decisions

* **Data APIs**: NYC Open Data (Socrata) — app token available. Census API — key available.
* **Database**: Supabase (PostgreSQL) — instance available.
* **Frontend hosting**: Vercel.
* **Mapping**: MapLibre GL JS.
