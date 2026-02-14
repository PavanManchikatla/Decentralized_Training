import { Link } from 'react-router-dom'
import PolicyControls from '../components/PolicyControls'
import { useNodesRealtime } from '../hooks/useNodesRealtime'
import { formatNumber, secondsSince, toPercent } from '../utils'

export default function DevicesPage() {
  const { nodes, loading, error, saveNodePolicy } = useNodesRealtime()

  return (
    <section className="page">
      <header>
        <h1>Devices</h1>
      </header>

      {loading && <p>Loading devices...</p>}
      {error && <p>{error}</p>}

      <section className="devices-grid">
        {nodes.map((node) => {
          const vramPercent = toPercent(node.metrics.vram_used_gb, node.capabilities.vram_total_gb)

          return (
            <article key={node.identity.node_id} className="surface device-card">
              <div className="device-card-head">
                <h2>
                  <Link to={`/devices/${encodeURIComponent(node.identity.node_id)}`}>
                    {node.identity.display_name}
                  </Link>
                </h2>
                <span className="status-pill">{node.status}</span>
              </div>

              <p>Last heartbeat age: {secondsSince(node.last_seen)}s</p>
              <p>
                Capabilities: {node.capabilities.cpu_threads ?? '-'} threads,{' '}
                {formatNumber(node.capabilities.ram_total_gb ?? 0, 1)} GB RAM
                {node.capabilities.gpu_name
                  ? `, ${node.capabilities.gpu_name} (${formatNumber(node.capabilities.vram_total_gb ?? 0, 1)} GB VRAM)`
                  : ''}
              </p>
              <p>
                Metrics: CPU {formatNumber(node.metrics.cpu_percent, 1)}%, RAM{' '}
                {formatNumber(node.metrics.ram_percent, 1)}%
                {node.metrics.gpu_percent !== null
                  ? `, GPU ${formatNumber(node.metrics.gpu_percent, 1)}%`
                  : ''}
                {vramPercent !== null ? `, VRAM ${formatNumber(vramPercent, 1)}%` : ''}
              </p>
              <p>Running jobs: {node.metrics.running_jobs}</p>

              <PolicyControls
                node={node}
                onPolicyChange={async (policy) => {
                  await saveNodePolicy(node.identity.node_id, policy)
                }}
              />
            </article>
          )
        })}
      </section>
    </section>
  )
}
