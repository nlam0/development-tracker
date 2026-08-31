-- Decision D6(b): admit study-area lots that PLUTO gives no centroid for by
-- block membership, rather than leaving them permanently outside the study
-- area. 10 such lots sit on study-area blocks, including the Essex Crossing
-- parcels and a Two Bridges condo lot -- disproportionately the air-rights
-- and condo lots where the largest development happens (Risk R12).
--
-- How a BBL entered the study area is itself research metadata, so it is
-- recorded per row rather than inferred: 'centroid' is the direct
-- point-in-polygon result, 'block_membership' is the D6(b) fallback and is
-- a weaker claim, surfaced on /methodology.
ALTER TABLE study_area_bbls
  ADD COLUMN resolution_method TEXT NOT NULL DEFAULT 'centroid';

ALTER TABLE study_area_bbls
  ADD CONSTRAINT study_area_bbls_resolution_method_check
  CHECK (resolution_method IN ('centroid', 'block_membership'));

-- Existing rows are all centroid-resolved; drop the default so every future
-- insert has to state its method explicitly.
ALTER TABLE study_area_bbls ALTER COLUMN resolution_method DROP DEFAULT;
