# edgemesh

`edgemesh` is a monorepo with three services:

- `coordinator/`: FastAPI coordinator API with SQLite persistence, distributed task execution, scheduling simulation, and SSE streams.
- `agent/`: Python edge agent that registers capabilities, sends heartbeats, pulls tasks, executes them locally, and reports results.
- `ui/`: React + Vite dashboard.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+
- npm 10+

## Setup

1. Coordinator:

```bash
cd coordinator
uv sync --dev
cp .env.example .env
```

2. Agent:

```bash
cd ../agent
uv sync --dev
cp .env.example .env
```

3. UI:

```bash
cd ../ui
npm install
```

## Run (single command per terminal window)

Use these exact one-liners in three separate terminal windows in the project repo:

```bash
make coordinator-dev
make agent-dev
make ui-dev
```

Open [http://localhost:5173/devices](http://localhost:5173/devices).

If you already opened a shell inside the repo root, you can run:

```bash
make coordinator-dev
make agent-dev
make ui-dev
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for topology, flow diagrams, and module map.

## Serve Built UI from Coordinator

```bash
cd ui
npm run build
cd ..
make coordinator-dev
```

Then open [http://localhost:8000](http://localhost:8000). Coordinator serves `ui/dist/index.html` on `/` and static assets on `/assets/*`.

## Security Model (MVP)

- Agent-to-coordinator endpoints (`/v1/agent/register`, `/v1/agent/heartbeat`, `/v1/tasks/*`, and legacy `/api/agents/*`) require the shared secret when `EDGE_MESH_SHARED_SECRET` is set.
- Agent sends `X-EdgeMesh-Secret: <EDGE_MESH_SHARED_SECRET>`.
- UI endpoints remain unauthenticated for local development.
- This is local-only MVP auth and is not a replacement for full user/session auth.

## Coordinator APIs

- `GET /health`
- `GET /v1/nodes`
- `GET /v1/nodes/{node_id}`
- `PUT /v1/nodes/{node_id}/policy`
- `GET /v1/stream/nodes` (SSE)
- `GET /v1/cluster/summary`
- `POST /v1/agent/register`
- `POST /v1/agent/heartbeat`
- `POST /v1/tasks/pull`
- `POST /v1/tasks/{task_id}/result`
- `GET /v1/metrics/execution`
- `POST /v1/simulate/schedule`
- `POST /v1/jobs`
- `GET /v1/jobs`
- `GET /v1/jobs/{job_id}`
- `GET /v1/jobs/{job_id}/tasks`
- `POST /v1/jobs/{job_id}/status`
- `POST /v1/demo/jobs/create-embed-burst?count=20`

## Quick Verification (Phase 1.5)

1. Health:

```bash
curl http://localhost:8000/health
```

2. Submit distributed demo jobs:

```bash
curl -X POST "http://localhost:8000/v1/demo/jobs/create-embed-burst?count=20&tasks_per_job=6"
```

3. Watch jobs/tasks progress while agent is running:

```bash
curl http://localhost:8000/v1/jobs
curl http://localhost:8000/v1/jobs/<job_id>/tasks
```

4. Execution metrics:

```bash
curl http://localhost:8000/v1/metrics/execution
```

5. Secret check (should be 401 when secret is configured):

```bash
curl -X POST http://localhost:8000/v1/tasks/pull -H 'content-type: application/json' -d '{"node_id":"n1"}'
```

## Notes

- `NODE_STALE_SECONDS` defaults to `15`; stale scan runs every `5` seconds.
- `TASK_LEASE_SECONDS` defaults to `30`; stale task recovery runs every `3` seconds.
- Agent persists node identity in `agent/state/node_id.txt`.
- Scheduler eligibility is policy-driven; lowering caps immediately affects simulation results and cluster summary totals.
