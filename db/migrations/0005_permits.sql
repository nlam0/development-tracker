-- DOB NOW (M4) + DOB legacy (M8), unified. Many rows per BBL.
CREATE TABLE permits (
  id             BIGSERIAL PRIMARY KEY,
  source         TEXT NOT NULL,          -- 'dob_now' | 'dob_legacy'
  external_id    TEXT NOT NULL,          -- see IMPLEMENTATION_PLAN.md §4 for per-source derivation
  bbl            CHAR(10) REFERENCES parcels(bbl),
  bin            TEXT,
  address        TEXT,
  filing_number  TEXT,
  permit_type    TEXT,                   -- raw source value
  work_type      TEXT,                   -- raw source value
  category       TEXT NOT NULL,          -- canonical: new_building|alteration|demolition|other
  filing_reason  TEXT,
  status         TEXT,
  description    TEXT,
  estimated_cost NUMERIC(14,2),          -- parsed from text (Risk R5)
  approved_date  DATE,
  issued_date    DATE,
  expired_date   DATE,
  event_date     DATE NOT NULL,          -- canonical cross-source chronological sort column
  latitude       DOUBLE PRECISION,
  longitude      DOUBLE PRECISION,
  geom           GEOMETRY(Point, 4326),
  owner_name     TEXT,
  raw            JSONB,                  -- source record as received
  retrieved_at   TIMESTAMPTZ NOT NULL,
  CONSTRAINT permits_natural_key UNIQUE (source, external_id)
);

CREATE INDEX permits_bbl_idx        ON permits (bbl);
CREATE INDEX permits_event_date_idx ON permits (event_date DESC);
CREATE INDEX permits_category_idx   ON permits (category);
CREATE INDEX permits_geom_idx       ON permits USING GIST (geom);
CREATE INDEX permits_feed_idx       ON permits (event_date DESC, category, estimated_cost);
