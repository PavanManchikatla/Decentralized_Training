import { useEffect, useState } from 'react'
import type { Node, NodePolicy, RolePreference, TaskType } from '../types'

const TASK_TYPES: TaskType[] = ['INFERENCE', 'EMBEDDINGS', 'PREPROCESS']
const ROLE_OPTIONS: RolePreference[] = [
  'AUTO',
  'PREFER_INFERENCE',
  'PREFER_EMBEDDINGS',
  'PREFER_PREPROCESS',
]

type Props = {
  node: Node
  onPolicyChange: (policy: NodePolicy) => Promise<void>
}

function uniqueTaskTypes(values: TaskType[]): TaskType[] {
  const output: TaskType[] = []
  values.forEach((value) => {
    if (!output.includes(value)) {
      output.push(value)
    }
  })
  return output
}

export default function PolicyControls({ node, onPolicyChange }: Props) {
  const [policy, setPolicy] = useState<NodePolicy>(node.policy)

  useEffect(() => {
    setPolicy(node.policy)
  }, [node.identity.node_id, node.policy])

  const commit = async (next: NodePolicy) => {
    setPolicy(next)
    await onPolicyChange(next)
  }

  const setCpuCap = (value: number) =>
    void commit({
      ...policy,
      cpu_cap_percent: value,
    })

  const setRamCap = (value: number) =>
    void commit({
      ...policy,
      ram_cap_percent: value,
    })

  const setGpuCap = (value: number) =>
    void commit({
      ...policy,
      gpu_cap_percent: value,
    })

  const toggleTask = (taskType: TaskType) => {
    const taskAllowlist = policy.task_allowlist.includes(taskType)
      ? policy.task_allowlist.filter((value) => value !== taskType)
      : [...policy.task_allowlist, taskType]

    void commit({
      ...policy,
      task_allowlist: uniqueTaskTypes(taskAllowlist),
    })
  }

  return (
    <section className="policy-panel">
      <label className="row-control">
        <span>Enabled</span>
        <input
          type="checkbox"
          checked={policy.enabled}
          onChange={(event) => {
            void commit({
              ...policy,
              enabled: event.target.checked,
            })
          }}
        />
      </label>

      <label className="row-control">
        <span>CPU cap {policy.cpu_cap_percent}%</span>
        <input
          type="range"
          min={0}
          max={100}
          value={policy.cpu_cap_percent}
          onChange={(event) => {
            setCpuCap(Number(event.target.value))
          }}
        />
      </label>

      <label className="row-control">
        <span>RAM cap {policy.ram_cap_percent}%</span>
        <input
          type="range"
          min={0}
          max={100}
          value={policy.ram_cap_percent}
          onChange={(event) => {
            setRamCap(Number(event.target.value))
          }}
        />
      </label>

      {node.capabilities.has_gpu && (
        <label className="row-control">
          <span>GPU cap {policy.gpu_cap_percent ?? 100}%</span>
          <input
            type="range"
            min={0}
            max={100}
            value={policy.gpu_cap_percent ?? 100}
            onChange={(event) => {
              setGpuCap(Number(event.target.value))
            }}
          />
        </label>
      )}

      <fieldset className="field-group">
        <legend>Task allowlist</legend>
        {TASK_TYPES.map((taskType) => (
          <label key={taskType} className="task-option">
            <input
              type="checkbox"
              checked={policy.task_allowlist.includes(taskType)}
              onChange={() => {
                toggleTask(taskType)
              }}
            />
            <span>{taskType}</span>
          </label>
        ))}
      </fieldset>

      <label className="row-control">
        <span>Role preference</span>
        <select
          value={policy.role_preference}
          onChange={(event) => {
            void commit({
              ...policy,
              role_preference: event.target.value as RolePreference,
            })
          }}
        >
          {ROLE_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
    </section>
  )
}
