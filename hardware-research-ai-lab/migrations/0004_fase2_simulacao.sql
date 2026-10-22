CREATE TABLE third_party_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  simulator TEXT NOT NULL,
  sample TEXT NOT NULL,
  commit_hash TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  reviewed_at TEXT NOT NULL,
  summary_json TEXT NOT NULL,
  approved_by TEXT,
  approved_at TEXT,
  UNIQUE (simulator, sample, fingerprint)
);
CREATE TABLE simulation_builds (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  simulator TEXT NOT NULL,
  sample TEXT NOT NULL,
  commit_hash TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  toolchain TEXT NOT NULL,
  binary_path TEXT NOT NULL,
  binary_sha256 TEXT NOT NULL,
  built_at TEXT NOT NULL,
  duration_ms INTEGER NOT NULL
);
CREATE TABLE simulation_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  simulator TEXT NOT NULL,
  sample TEXT NOT NULL,
  commit_hash TEXT NOT NULL,
  binary_sha256 TEXT NOT NULL,
  args_json TEXT NOT NULL,
  sandbox_json TEXT NOT NULL,
  started_at TEXT NOT NULL,
  duration_ms INTEGER NOT NULL,
  exit_code INTEGER NOT NULL,
  timed_out INTEGER NOT NULL DEFAULT 0,
  verified INTEGER NOT NULL DEFAULT 0,
  experiment_id TEXT REFERENCES experiments(id),
  note TEXT
);
