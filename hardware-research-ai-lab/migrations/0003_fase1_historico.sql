CREATE TABLE source_verifications (
  source_id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('verificado','parcial','inacessivel')),
  checked_at TEXT NOT NULL,
  head_commit TEXT,
  head_date TEXT,
  license_detected TEXT,
  license_matches INTEGER,
  http_status INTEGER,
  note TEXT NOT NULL
);
CREATE TABLE commit_findings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id TEXT NOT NULL,
  hash TEXT NOT NULL,
  commit_date TEXT NOT NULL,
  subject TEXT NOT NULL,
  is_revert INTEGER NOT NULL DEFAULT 0,
  reverted_hash TEXT,
  keywords_json TEXT NOT NULL,
  issue_refs_json TEXT NOT NULL,
  scanned_at TEXT NOT NULL,
  UNIQUE (source_id, hash)
);
CREATE INDEX idx_findings_source ON commit_findings(source_id);
