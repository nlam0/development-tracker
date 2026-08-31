-- Decision D7(b): a permit enters the study area either because its BBL is in
-- the allowlist, or because its own point falls inside a study-area polygon.
-- Without the spatial arm, 272 of 8,721 in-polygon permits (3.1%) are dropped
-- silently -- null BBLs, condo unit lots, and merged/demapped lots (Risk R12).
--
-- A spatially-matched permit has no parcels row to join through, so it cannot
-- borrow a neighborhood from `parcels` the way a BBL-matched permit can. The
-- feed and map filter by neighborhood constantly (PRD §7A, §7B), so permits
-- carry their own -- otherwise every spatially-matched permit would vanish the
-- moment any neighborhood filter is applied.
ALTER TABLE permits
  ADD COLUMN neighborhood TEXT REFERENCES study_areas(name) ON UPDATE CASCADE,
  ADD COLUMN study_area_match TEXT NOT NULL DEFAULT 'bbl';

-- How the permit was tied to the study area, surfaced in the UI and on
-- /methodology so a spatial match is never presented as a parcel-level fact.
ALTER TABLE permits
  ADD CONSTRAINT permits_study_area_match_check
  CHECK (study_area_match IN ('bbl', 'spatial'));

-- permits is still empty (M4 not built); drop the default so the adapter has
-- to state the match type for every row it writes.
ALTER TABLE permits ALTER COLUMN study_area_match DROP DEFAULT;

CREATE INDEX permits_neighborhood_idx ON permits (neighborhood);
