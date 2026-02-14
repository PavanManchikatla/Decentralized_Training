import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from api.state import node_event_bus

router = APIRouter(prefix="/v1/stream", tags=["stream"])


@router.get("/nodes")
async def stream_nodes(request: Request) -> StreamingResponse:
    """Server-Sent Events stream for node updates.

    Emits `node_update` events whenever heartbeat metrics are updated or when a node status changes.

    Example event payload:
    {
      "node_id": "node-1",
      "status": "ONLINE",
      "metrics": {
        "cpu_percent": 34.0,
        "gpu_percent": 55.0,
        "ram_percent": 63.0,
        "running_jobs": 1,
        "heartbeat_ts": "2026-02-14T01:00:00Z",
        "extra": {"uptime_seconds": 120.0}
      },
      "updated_at": "2026-02-14T01:00:00Z"
    }
    """

    async def generator():
        queue = await node_event_bus.subscribe()
        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: node_update\ndata: {event.model_dump_json()}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            await node_event_bus.unsubscribe(queue)

    return StreamingResponse(generator(), media_type="text/event-stream")
