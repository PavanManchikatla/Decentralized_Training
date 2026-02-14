import type {
  ClusterSummary,
  Node,
  NodeDetail,
  NodePolicy,
  NodeUpdateEvent,
} from '../types'

const BASE_URL = import.meta.env.VITE_COORDINATOR_URL?.trim() ?? ''

function apiUrl(path: string): string {
  if (!BASE_URL) {
    return path
  }
  return `${BASE_URL}${path}`
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      'content-type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }

  return (await response.json()) as T
}

export async function getNodes(): Promise<Node[]> {
  return fetchJson<Node[]>('/v1/nodes')
}

export async function getNodeDetail(nodeId: string, historyLimit = 180): Promise<NodeDetail> {
  const query = new URLSearchParams({
    include_metrics_history: 'true',
    history_limit: String(historyLimit),
  })
  return fetchJson<NodeDetail>(`/v1/nodes/${encodeURIComponent(nodeId)}?${query.toString()}`)
}

export async function updateNodePolicy(nodeId: string, policy: NodePolicy): Promise<Node> {
  return fetchJson<Node>(`/v1/nodes/${encodeURIComponent(nodeId)}/policy`, {
    method: 'PUT',
    body: JSON.stringify(policy),
  })
}

export async function getClusterSummary(): Promise<ClusterSummary> {
  return fetchJson<ClusterSummary>('/v1/cluster/summary')
}

export function openNodesStream(onEvent: (event: NodeUpdateEvent) => void, onError: () => void): EventSource {
  const source = new EventSource(apiUrl('/v1/stream/nodes'))

  source.addEventListener('node_update', (event) => {
    const message = event as MessageEvent<string>
    const payload = JSON.parse(message.data) as NodeUpdateEvent
    onEvent(payload)
  })

  source.onerror = () => {
    onError()
  }

  return source
}
