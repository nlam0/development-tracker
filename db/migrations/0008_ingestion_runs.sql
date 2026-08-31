-- Audit log: one row per pipeline execution, success or failure (PRD §10, §14).
CREATE TABLE ingestion_runs (
  id               BIGSERIAL PRIMARY KEY,
  source           TEXT NOT NULL,
  started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at     TIMESTAMPTZ,
  cursor_start     TEXT,                  -- incremental watermark used
  cursor_end       TEXT,                  -- watermark to resume from next run
  records_received INTEGER NOT NULL DEFAULT 0,
  records_inserted INTEGER NOT NULL DEFAULT 0,
  records_updated  INTEGER NOT NULL DEFAULT 0,
  records_rejected INTEGER NOT NULL DEFAULT 0,
  status           TEXT NOT NULL,         -- 'running' | 'success' | 'failed'
  error_message    TEXT
);

CREATE INDEX ingestion_runs_source_idx ON ingestion_runs (source, started_at DESC);
