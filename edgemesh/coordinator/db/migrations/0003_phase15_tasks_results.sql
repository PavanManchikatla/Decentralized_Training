BEGIN;

CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL,
  assigned_node_id TEXT,
  retries INTEGER NOT NULL DEFAULT 0,
  max_retries INTEGER NOT NULL DEFAULT 2,
  lease_expires_at DATETIME,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  started_at DATETIME,
  completed_at DATETIME,
  error TEXT,
  FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
  FOREIGN KEY (assigned_node_id) REFERENCES nodes(node_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_job_id ON tasks(job_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned_node ON tasks(assigned_node_id);
CREATE INDEX IF NOT EXISTS idx_tasks_lease_expires ON tasks(lease_expires_at);

CREATE TABLE IF NOT EXISTS results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  success INTEGER NOT NULL,
  output_json TEXT,
  duration_ms INTEGER NOT NULL,
  created_at DATETIME NOT NULL,
  FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
  FOREIGN KEY (node_id) REFERENCES nodes(node_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_results_task_id ON results(task_id);
CREATE INDEX IF NOT EXISTS idx_results_node_id ON results(node_id);
CREATE INDEX IF NOT EXISTS idx_results_created_at ON results(created_at);

COMMIT;
