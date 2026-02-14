# agent

Python agent that persists a node identity, registers with coordinator, and sends heartbeats.

## Run

```bash
uv sync --dev
cp .env.example .env
PYTHONPATH=src uv run python main.py
```
