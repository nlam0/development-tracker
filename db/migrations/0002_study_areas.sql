-- Researcher-defined boundaries (PRD §5, IMPLEMENTATION_PLAN.md §3 and decision D1).
-- Explicitly not official administrative geography -- see definition_note per row.
CREATE TABLE study_areas (
  id              SERIAL PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,
  geom            GEOMETRY(MultiPolygon, 4326) NOT NULL,
  definition_note TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX study_areas_geom_idx ON study_areas USING GIST (geom);
