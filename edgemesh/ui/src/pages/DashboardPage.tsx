import { useEffect, useMemo, useState } from 'react'
import { getClusterSummary } from '../api/edgemesh'
import { useNodesRealtime } from '../hooks/useNodesRealtime'
import type { ClusterSummary } from '../types'
import { formatNumber } from '../utils'

export default function DashboardPage() {
  const { nodes } = useNodesRealtime()
  const [summary, setSummary] = useState<ClusterSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    const load = async () => {
      try {
        const payload = await getClusterSummary()
        if (active) {
          setSummary(payload)
          setError(null)
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : 'Failed to load summary')
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
  }, [])

  const topUtilized = useMemo(
    () =>
      [...nodes]
        .sort((left, right) => right.metrics.cpu_percent - left.metrics.cpu_percent)
        .slice(0, 5),
    [nodes],
  )

  return (
    <section className="page">
      <header>
        <h1>Cluster Summary</h1>
      </header>

      {error && <p>{error}</p>}

      <section className="summary-grid">
        <article className="surface">
          <h2>Total nodes</h2>
          <p>{summary?.total_nodes ?? 0}</p>
        </article>
        <article className="surface">
          <h2>Online nodes</h2>
          <p>{summary?.online_nodes ?? 0}</p>
        </article>
        <article className="surface">
          <h2>Offline nodes</h2>
          <p>{summary?.offline_nodes ?? 0}</p>
        </article>
        <article className="surface">
          <h2>Effective CPU threads</h2>
          <p>{formatNumber(summary?.total_effective_cpu_threads ?? 0, 2)}</p>
        </article>
        <article className="surface">
          <h2>Effective RAM GB</h2>
          <p>{formatNumber(summary?.total_effective_ram_gb ?? 0, 2)}</p>
        </article>
        <article className="surface">
          <h2>Effective VRAM GB</h2>
          <p>{formatNumber(summary?.total_effective_vram_gb ?? 0, 2)}</p>
        </article>
        <article className="surface">
          <h2>Active running jobs</h2>
          <p>{summary?.active_running_jobs_total ?? 0}</p>
        </article>
      </section>

      <section className="surface">
        <h2>Top utilized nodes</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Node</th>
                <th>Status</th>
                <th>CPU %</th>
                <th>RAM %</th>
                <th>Running jobs</th>
              </tr>
            </thead>
            <tbody>
              {topUtilized.map((node) => (
                <tr key={node.identity.node_id}>
                  <td>{node.identity.display_name}</td>
                  <td>{node.status}</td>
                  <td>{formatNumber(node.metrics.cpu_percent, 1)}</td>
                  <td>{formatNumber(node.metrics.ram_percent, 1)}</td>
                  <td>{node.metrics.running_jobs}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  )
}
