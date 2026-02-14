# edgemesh

`edgemesh` is a monorepo with three services:

- `coordinator/`: FastAPI coordinator API with SQLite persistence + SSE streaming.
- `agent/`: Python edge agent that registers capabilities and sends heartbeats.
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

## Run (separate terminals from repo root)

```bash
make coordinator-dev
make agent-dev
make ui-dev
```

Open [http://localhost:5173/devices](http://localhost:5173/devices).

## Serve Built UI from Coordinator

```bash
cd ui
npm run build
cd ..
make coordinator-dev
```

Then open [http://localhost:8000](http://localhost:8000). Coordinator serves `ui/dist/index.html` on `/` and static assets on `/assets/*`.

## Coordinator APIs

- `GET /health`
- `GET /v1/nodes`
- `GET /v1/nodes/{node_id}`
- `PUT /v1/nodes/{node_id}/policy`
- `GET /v1/stream/nodes` (SSE)
- `GET /v1/cluster/summary`
- `POST /v1/agent/register`
- `POST /v1/agent/heartbeat`
- `POST /v1/simulate/schedule`

## Notes

- `NODE_STALE_SECONDS` defaults to `15`; stale scan runs every `5` seconds.
- Agent persists node identity in `agent/state/node_id.txt`.
- Scheduler eligibility is policy-driven; lowering caps immediately affects simulation results.
