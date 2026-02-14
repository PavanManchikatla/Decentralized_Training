import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import LineChart from '../components/LineChart'
import PolicyControls from '../components/PolicyControls'
import { getNodeDetail } from '../api/edgemesh'
import { useNodesRealtime } from '../hooks/useNodesRealtime'
import type { NodeDetail } from '../types'
import { formatNumber, secondsSince } from '../utils'

export default function DeviceDetailPage() {
  const { nodeId } = useParams<{ nodeId: string }>()
  const { nodes, saveNodePolicy } = useNodesRealtime()

  const decodedNodeId = decodeURIComponent(nodeId ?? '')
  const node = nodes.find((entry) => entry.identity.node_id === decodedNodeId)

  const [detail, setDetail] = useState<NodeDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!decodedNodeId) {
      return
    }

    let active = true

    const load = async () => {
      try {
        const payload = await getNodeDetail(decodedNodeId, 220)
        if (active) {
          setDetail(payload)
          setError(null)
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : 'Failed to load node detail')
        }
      }
    }

    void load()
    const id = window.setInterval(() => {
      void load()
    }, 3000)

    return () => {
      active = false
      window.clearInterval(id)
    }
  }, [decodedNodeId])

  const history = useMemo(() => {
    const cutoff = Date.now() - 5 * 60 * 1000
    const samples = (detail?.metrics_history ?? [])
      .map((item) => ({
        timestamp: Date.parse(item.heartbeat_ts),
        cpu: item.cpu_percent,
        ram: item.ram_percent,
      }))
      .filter((sample) => !Number.isNaN(sample.timestamp) && sample.timestamp >= cutoff)

    if (samples.length === 0 && node) {
      return [
        {
          timestamp: Date.parse(node.metrics.heartbeat_ts),
          cpu: node.metrics.cpu_percent,
          ram: node.metrics.ram_percent,
        },
      ]
    }

    return samples
  }, [detail?.metrics_history, node])

  if (!node) {
    return (
      <section className="page">
        <h1>Device not found</h1>
      </section>
    )
  }

  return (
    <section className="page">
      <header>
        <h1>{node.identity.display_name}</h1>
      </header>

      {error && <p>{error}</p>}

      <section className="surface">
        <p>Status: {node.status}</p>
        <p>Last heartbeat age: {secondsSince(node.last_seen)}s</p>
        <p>IP: {node.identity.ip}</p>
        <p>CPU: {formatNumber(node.metrics.cpu_percent, 1)}%</p>
        <p>RAM: {formatNumber(node.metrics.ram_percent, 1)}%</p>
      </section>

      <section className="charts-grid">
        <LineChart
          title="CPU % (last 5 minutes)"
          points={history.map((item) => ({ timestamp: item.timestamp, value: item.cpu }))}
        />
        <LineChart
          title="RAM % (last 5 minutes)"
          points={history.map((item) => ({ timestamp: item.timestamp, value: item.ram }))}
        />
      </section>

      <section className="surface">
        <h2>Policy</h2>
        <PolicyControls
          node={node}
          onPolicyChange={async (policy) => {
            await saveNodePolicy(node.identity.node_id, policy)
          }}
        />
      </section>
    </section>
  )
}
