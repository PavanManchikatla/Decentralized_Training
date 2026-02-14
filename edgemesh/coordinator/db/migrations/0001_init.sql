BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nodes (
  node_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  ip TEXT NOT NULL,
  port INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'UNKNOWN',
  capabilities_json TEXT NOT NULL,
  metrics_json TEXT NOT NULL,
  policy_json TEXT NOT NULL,
  last_seen DATETIME NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nodes_status ON nodes(status);
CREATE INDEX IF NOT EXISTS idx_nodes_last_seen ON nodes(last_seen);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  status TEXT NOT NULL,
  assigned_node_id TEXT,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  error TEXT,
  FOREIGN KEY (assigned_node_id) REFERENCES nodes(node_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_node ON jobs(assigned_node_id);

COMMIT;
