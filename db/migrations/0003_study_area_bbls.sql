-- The authoritative BBL allowlist derived from study_areas via point-in-polygon
-- (IMPLEMENTATION_PLAN.md M1). This is the single input every later adapter's
-- "filter to study area" pipeline stage (PRD §8) reads from -- ingestion never
-- re-derives or hardcodes the study-area block/BBL set itself.
CREATE TABLE study_area_bbls (
  bbl           CHAR(10) PRIMARY KEY,
  study_area_id INTEGER NOT NULL REFERENCES study_areas(id),
  resolved_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX study_area_bbls_study_area_id_idx ON study_area_bbls (study_area_id);
