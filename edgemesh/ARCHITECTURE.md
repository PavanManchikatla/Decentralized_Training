# EdgeMesh Architecture (Phase 1.5)

This document maps the system from job submission to distributed task completion across trusted LAN nodes.

## System Topology

```mermaid
flowchart LR
    U["User (Browser UI)"] --> UI["React UI (Vite)"]
    UI -->|REST/SSE| C["Coordinator (FastAPI)"]
    A1["Agent Node A\nCPU/GPU"] -->|register/heartbeat| C
    A2["Agent Node B\nCPU-only"] -->|register/heartbeat| C
    A3["Agent Node C\nCPU-only"] -->|register/heartbeat| C

    A1 -->|pull task / submit result| C
    A2 -->|pull task / submit result| C
    A3 -->|pull task / submit result| C

    C --> DB[("SQLite DB\n(nodes, jobs, tasks, results)")]
    C --> SSE["SSE Streams\n/v1/stream/nodes\n/v1/stream/jobs"]
    SSE --> UI
```

## Execution Flow

```mermaid
sequenceDiagram
    participant User
    participant UI
    participant Coord as Coordinator
    participant DB as SQLite
    participant Agent as Agent Worker

    User->>UI: Create job (task_type, payload_ref/task_count)
    UI->>Coord: POST /v1/jobs
    Coord->>DB: insert job + split into task rows (QUEUED)
    Coord-->>UI: job created with progress fields

    loop Poll loop
      Agent->>Coord: POST /v1/tasks/pull (node_id)
      Coord->>DB: choose eligible QUEUED task using policy/scheduler
      Coord->>DB: mark task RUNNING + lease_expires_at
      Coord-->>Agent: task payload
      Agent->>Agent: execute locally
      Agent->>Coord: POST /v1/tasks/{id}/result (success/fail,duration,output)
      Coord->>DB: store result + update task status
      Coord->>DB: aggregate job progress/status
      Coord-->>UI: SSE job_update
    end

    Note over Coord,DB: stale task lease recovery requeues or fails tasks by retry policy
```

## Key Modules

- `coordinator/app/coordinator_service/main.py`
: app startup, router wiring, background monitors.
- `coordinator/db/repository.py`
: persistence, scheduling-aware task pull, result aggregation, retries, metrics.
- `coordinator/api/routers/tasks.py`
: pull-based execution endpoints.
- `coordinator/api/routers/jobs.py`
: job creation, task splitting, task listing, progress publication.
- `coordinator/api/routers/stream.py`
: node/job SSE streams.
- `agent/src/agent_service/main.py`
: register + heartbeat + worker loop (pull/execute/report).
- `ui/src/pages/DevicesPage.tsx`
: live node status/policy controls.
- `ui/src/pages/JobsPage.tsx`
: job progress + task-level visibility.

## Security Boundaries

- Agent ingress endpoints require `X-EdgeMesh-Secret` when `EDGE_MESH_SHARED_SECRET` is configured.
- UI APIs are intentionally unauthenticated for local/LAN MVP usage.
- Trusted-network assumption: Phase 1.5 targets private LAN mesh.
