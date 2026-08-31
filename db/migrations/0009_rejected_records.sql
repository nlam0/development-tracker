-- Records that failed validation. Logged, never silently dropped (PRD §14).
CREATE TABLE rejected_records (
  id         BIGSERIAL PRIMARY KEY,
  run_id     BIGINT REFERENCES ingestion_runs(id),
  source     TEXT NOT NULL,
  reason     TEXT NOT NULL,
  raw        JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
