-- Neighborhood-level ACS (M8). Keyed by geography, never by BBL (PRD §6).
CREATE TABLE census_context (
  geography_id    TEXT NOT NULL,           -- census tract GEOID
  geography_type  TEXT NOT NULL DEFAULT 'tract',
  tract_vintage   SMALLINT NOT NULL,       -- 2010 or 2020; boundaries differ (Risk R11)
  year            SMALLINT NOT NULL,       -- ACS5 vintage: 2014 | 2019 | 2024
  variable        TEXT NOT NULL,           -- e.g. 'B19013_001E'
  variable_label  TEXT,
  value           NUMERIC,
  margin_of_error NUMERIC,
  retrieved_at    TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (geography_id, tract_vintage, year, variable)
);
