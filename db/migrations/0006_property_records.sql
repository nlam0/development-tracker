-- ACRIS documents (M8). Many rows per BBL.
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
