CREATE TABLE command_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  time TEXT NOT NULL,
  command TEXT NOT NULL,
  args_json TEXT NOT NULL,
  exit_code INTEGER NOT NULL,
  duration TEXT NOT NULL,
  timed_out INTEGER NOT NULL DEFAULT 0,
  error TEXT
);
