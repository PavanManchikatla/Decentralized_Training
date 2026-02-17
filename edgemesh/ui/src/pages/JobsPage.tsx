import { useEffect, useMemo, useState } from 'react'
import {
  createDemoEmbedBurst,
  getJobs,
  getJobTasks,
  openJobsStream,
} from '../api/edgemesh'
import type { Job, JobStatus, Task, TaskType } from '../types'

const STATUS_OPTIONS: Array<JobStatus | 'ALL'> = [
  'ALL',
  'QUEUED',
  'RUNNING',
  'COMPLETED',
  'FAILED',
  'CANCELLED',
]
const TASK_OPTIONS: Array<TaskType | 'ALL'> = [
  'ALL',
  'INFERENCE',
  'EMBEDDINGS',
  'INDEX',
  'TOKENIZE',
  'PREPROCESS',
]

function formatDuration(job: Job): string {
  const start = job.started_at ? Date.parse(job.started_at) : Number.NaN

  if (Number.isNaN(start)) {
    return '-'
  }

  const end = job.completed_at ? Date.parse(job.completed_at) : Date.now()
  if (Number.isNaN(end) || end < start) {
    return '-'
  }

  return `${Math.floor((end - start) / 1000)}s`
}

function formatTimestamp(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleTimeString()
}

function progressPercent(job: Job): number {
  if (job.total_tasks <= 0) {
    return 0
  }
  return Math.round((job.completed_tasks / job.total_tasks) * 100)
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<JobStatus | 'ALL'>('ALL')
  const [taskFilter, setTaskFilter] = useState<TaskType | 'ALL'>('ALL')
  const [busy, setBusy] = useState(false)
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [selectedJobTasks, setSelectedJobTasks] = useState<Task[]>([])

  useEffect(() => {
    let active = true

    const load = async () => {
      try {
        const payload = await getJobs({
          status: statusFilter,
          taskType: taskFilter,
        })
        if (!active) {
          return
        }
        setJobs(payload)
        setError(null)
      } catch (err) {
        if (!active) {
          return
        }
        setError(err instanceof Error ? err.message : 'Failed to load jobs')
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    void load()

    const stream = openJobsStream(
      () => {
        void load()
      },
      () => {
        // polling below remains the fallback and baseline refresh path
      }
    )

    const id = window.setInterval(() => {
      void load()
    }, 5000)

    return () => {
      active = false
      stream.close()
      window.clearInterval(id)
    }
  }, [statusFilter, taskFilter])

  useEffect(() => {
    if (!selectedJobId) {
      setSelectedJobTasks([])
      return
    }

    let active = true
    const loadTasks = async () => {
      try {
        const payload = await getJobTasks(selectedJobId)
        if (active) {
          setSelectedJobTasks(payload)
        }
      } catch {
        if (active) {
          setSelectedJobTasks([])
        }
      }
    }

    void loadTasks()
    const id = window.setInterval(() => {
      void loadTasks()
    }, 5000)

    return () => {
      active = false
      window.clearInterval(id)
    }
  }, [selectedJobId])

  const sortedJobs = useMemo(
    () =>
      [...jobs].sort(
        (left, right) =>
          Date.parse(right.created_at) - Date.parse(left.created_at)
      ),
    [jobs]
  )

  const triggerDemoBurst = async () => {
    setBusy(true)
    try {
      await createDemoEmbedBurst(20, 6)
      const payload = await getJobs({
        status: statusFilter,
        taskType: taskFilter,
      })
      setJobs(payload)
      setError(null)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to create demo jobs'
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="page">
      <header>
        <h1>Jobs</h1>
      </header>

      <section className="surface jobs-controls">
        <label>
          Task type{' '}
          <select
            value={taskFilter}
            onChange={(event) =>
              setTaskFilter(event.target.value as TaskType | 'ALL')
            }
          >
            {TASK_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label>
          Status{' '}
          <select
            value={statusFilter}
            onChange={(event) =>
              setStatusFilter(event.target.value as JobStatus | 'ALL')
            }
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          onClick={() => void triggerDemoBurst()}
          disabled={busy}
        >
          {busy ? 'Creating...' : 'Create Demo Embed Burst'}
        </button>
      </section>

      {loading && <p>Loading jobs...</p>}
      {error && <p>{error}</p>}

      <section className="surface table-wrap">
        <table>
          <thead>
            <tr>
              <th>job_id</th>
              <th>task_type</th>
              <th>status</th>
              <th>progress</th>
              <th>nodes</th>
              <th>created_at</th>
              <th>duration</th>
              <th>retries</th>
              <th>error</th>
            </tr>
          </thead>
          <tbody>
            {sortedJobs.map((job) => (
              <tr key={job.id} onClick={() => setSelectedJobId(job.id)}>
                <td>{job.id}</td>
                <td>{job.type}</td>
                <td>{job.status}</td>
                <td>
                  {job.completed_tasks}/{job.total_tasks} (
                  {progressPercent(job)}%)
                </td>
                <td>
                  {job.assigned_nodes.length > 0
                    ? job.assigned_nodes.join(', ')
                    : '-'}
                </td>
                <td>{formatTimestamp(job.created_at)}</td>
                <td>{formatDuration(job)}</td>
                <td>{job.total_retries}</td>
                <td>{job.error ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {selectedJobId && (
        <section className="surface table-wrap">
          <h2>Tasks for {selectedJobId}</h2>
          <table>
            <thead>
              <tr>
                <th>task_id</th>
                <th>status</th>
                <th>node</th>
                <th>retries</th>
                <th>completed_at</th>
                <th>error</th>
              </tr>
            </thead>
            <tbody>
              {selectedJobTasks.map((task) => (
                <tr key={task.id}>
                  <td>{task.id}</td>
                  <td>{task.status}</td>
                  <td>{task.assigned_node_id ?? '-'}</td>
                  <td>
                    {task.retries}/{task.max_retries}
                  </td>
                  <td>
                    {task.completed_at
                      ? formatTimestamp(task.completed_at)
                      : '-'}
                  </td>
                  <td>{task.error ?? '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </section>
  )
}
