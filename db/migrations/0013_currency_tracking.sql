-- Both current adapters are full reloads of the study area's upstream state
-- (see pipeline/sources/*.py module docstrings), but they only ever upserted.
-- A record that disappears upstream -- a permit revoked or superseded, a lot
-- merged or demapped out of PLUTO -- was never reconciled, so it stayed in the
-- database indefinitely, indistinguishable from one confirmed by this
-- morning's run. Nothing is stale today; this is the mechanism that keeps
-- that true rather than a repair.
--
-- Not a hard delete. This is research infrastructure: a permit that vanishes
-- from DOB's published set is itself a finding, and deleting it would destroy
-- the only record that it was ever filed. `is_current` marks presence in the
-- most recent successful full scan; `retrieved_at` already records when that
-- scan last saw the row, so the pair answers both "is this live?" and "how do
-- we know?".
ALTER TABLE parcels ADD COLUMN is_current BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE permits ADD COLUMN is_current BOOLEAN NOT NULL DEFAULT TRUE;

-- Partial indexes: the interesting query is "what went missing", and the
-- not-current set is expected to stay very small relative to the tables.
CREATE INDEX parcels_not_current_idx ON parcels (bbl) WHERE NOT is_current;
CREATE INDEX permits_not_current_idx ON permits (source, external_id) WHERE NOT is_current;

-- Audit counterpart in the run log (PRD §14 / Risk R8): a run that suddenly
-- marks thousands of rows absent is far more likely to be an upstream schema
-- or filter change than a real demolition wave, and that has to be visible in
-- the same place the other per-run counts are.
ALTER TABLE ingestion_runs ADD COLUMN records_marked_absent INTEGER NOT NULL DEFAULT 0;
