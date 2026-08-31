-- parcels.neighborhood references study_areas(name) -- a natural key that is
-- also editable research metadata. Without ON UPDATE CASCADE, renaming a
-- study area fails outright once parcels reference it, which would make a
-- boundary/naming revision a manual data-surgery job rather than an UPDATE.
-- (The name has already moved once: the plan drafted 'LES (adjacent)', the
-- loaded data says 'Lower East Side'.)
ALTER TABLE parcels DROP CONSTRAINT parcels_neighborhood_fkey;

ALTER TABLE parcels
  ADD CONSTRAINT parcels_neighborhood_fkey
  FOREIGN KEY (neighborhood) REFERENCES study_areas(name) ON UPDATE CASCADE;
