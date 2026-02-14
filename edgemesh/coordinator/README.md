# coordinator

FastAPI coordinator with SQLite persistence, SSE node updates, and scheduling simulation.

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
```

## Agent Ingest APIs

```bash
curl -X POST http://localhost:8000/v1/agent/register -H 'content-type: application/json' -d @register.json
curl -X POST http://localhost:8000/v1/agent/heartbeat -H 'content-type: application/json' -d @heartbeat.json
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
