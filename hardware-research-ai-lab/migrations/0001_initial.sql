CREATE TABLE hardware_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  collected_at TEXT NOT NULL,
  origin TEXT NOT NULL CHECK (origin IN ('measured','simulated','estimated','fixture')),
  payload_json TEXT NOT NULL
);
CREATE TABLE sources (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL,
  license TEXT NOT NULL,
  verification TEXT NOT NULL,
  last_commit_consulted TEXT,
  payload_json TEXT NOT NULL
);
CREATE TABLE tools (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('disponivel','ausente','incompativel','nao_testado')),
  version TEXT,
  path TEXT,
  checked_at TEXT,
  payload_json TEXT NOT NULL
);
CREATE TABLE experiments (
  id TEXT PRIMARY KEY,
  description TEXT NOT NULL,
  level TEXT NOT NULL CHECK (level IN ('A','B','C','D','E')),
  kind TEXT NOT NULL,
  origin TEXT NOT NULL CHECK (origin IN ('measured','simulated','estimated','fixture')),
  infrastructure_test INTEGER NOT NULL DEFAULT 0,
  evidence_state TEXT NOT NULL,
  created_at TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE TABLE evidences (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  experiment_id TEXT NOT NULL REFERENCES experiments(id),
  stance TEXT NOT NULL CHECK (stance IN ('favoravel','contraria')),
  url TEXT,
  summary TEXT NOT NULL,
  recorded_at TEXT NOT NULL
);
CREATE TABLE results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  experiment_id TEXT NOT NULL REFERENCES experiments(id),
  origin TEXT NOT NULL CHECK (origin IN ('measured','simulated','estimated','fixture')),
  metric TEXT NOT NULL,
  value REAL NOT NULL,
  unit TEXT NOT NULL,
  params_json TEXT NOT NULL,
  hardware_snapshot_id INTEGER REFERENCES hardware_snapshots(id),
  recorded_at TEXT NOT NULL
);
CREATE INDEX idx_results_experiment ON results(experiment_id);
CREATE INDEX idx_evidences_experiment ON evidences(experiment_id);
