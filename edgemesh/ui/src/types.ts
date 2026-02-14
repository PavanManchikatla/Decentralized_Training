export type NodeStatus = 'UNKNOWN' | 'ONLINE' | 'OFFLINE' | 'DEGRADED'
export type TaskType = 'INFERENCE' | 'EMBEDDINGS' | 'PREPROCESS'
export type RolePreference =
  | 'AUTO'
  | 'PREFER_INFERENCE'
  | 'PREFER_EMBEDDINGS'
  | 'PREFER_PREPROCESS'

export type NodeIdentity = {
  node_id: string
  display_name: string
  ip: string
  port: number
}

export type NodeCapabilities = {
  task_types: TaskType[]
  labels: string[]
  has_gpu: boolean
  cpu_cores: number | null
  cpu_threads: number | null
  ram_total_gb: number | null
  ram_gb: number | null
  gpu_name: string | null
  vram_total_gb: number | null
  os: string | null
  arch: string | null
}

export type NodeMetrics = {
  cpu_percent: number
  ram_used_gb: number
  ram_percent: number
  gpu_percent: number | null
  vram_used_gb: number | null
  running_jobs: number
  heartbeat_ts: string
  extra: Record<string, number>
}

export type NodePolicy = {
  enabled: boolean
  cpu_cap_percent: number
  gpu_cap_percent: number | null
  ram_cap_percent: number
  task_allowlist: TaskType[]
  role_preference: RolePreference
}

export type Node = {
  identity: NodeIdentity
  capabilities: NodeCapabilities
  metrics: NodeMetrics
  policy: NodePolicy
  status: NodeStatus
  last_seen: string
  created_at: string
  updated_at: string
}

export type NodeDetail = {
  node: Node
  metrics_history: NodeMetrics[] | null
}

export type NodeUpdateEvent = {
  node_id: string
  status: NodeStatus
  metrics: NodeMetrics
  updated_at: string
}

export type ClusterSummary = {
  total_nodes: number
  online_nodes: number
  offline_nodes: number
  total_effective_cpu_threads: number
  total_effective_ram_gb: number
  total_effective_vram_gb: number
  active_running_jobs_total: number
}
