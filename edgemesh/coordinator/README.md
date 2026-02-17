# coordinator

FastAPI coordinator with SQLite persistence, node SSE updates, distributed task execution APIs, and scheduling simulation.

## Run

```bash
uv sync --dev
cp .env.example .env
PYTHONPATH=app:. uv run python -m coordinator_service.main
```

## Key APIs

```bash
curl http://localhost:8000/health
curl http://localhost:8000/v1/nodes
curl -N http://localhost:8000/v1/stream/nodes
curl http://localhost:8000/v1/cluster/summary
curl -X POST http://localhost:8000/v1/simulate/schedule -H 'content-type: application/json' -d '{"task_type":"EMBED"}'
curl -X POST http://localhost:8000/v1/jobs -H 'content-type: application/json' -d '{"task_type":"EMBED","payload_ref":"demo://payload","task_count":4}'
curl -X POST 'http://localhost:8000/v1/demo/jobs/create-embed-burst?count=20&tasks_per_job=6'
curl http://localhost:8000/v1/metrics/execution
```

## Agent Ingest APIs

When `EDGE_MESH_SHARED_SECRET` is configured, include the header:

```bash
-H 'X-EdgeMesh-Secret: dev-shared-secret'
```

```bash
curl -X POST http://localhost:8000/v1/agent/register -H 'content-type: application/json' -H 'X-EdgeMesh-Secret: dev-shared-secret' -d @register.json
curl -X POST http://localhost:8000/v1/agent/heartbeat -H 'content-type: application/json' -H 'X-EdgeMesh-Secret: dev-shared-secret' -d @heartbeat.json
curl -X POST http://localhost:8000/v1/tasks/pull -H 'content-type: application/json' -H 'X-EdgeMesh-Secret: dev-shared-secret' -d '{"node_id":"node-1"}'
```

## Serve Built UI

From repository root:

```bash
cd ui
npm run build
cd ..
make coordinator-dev
```

Then open `http://localhost:8000`.
