import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from api.state import job_event_bus, node_event_bus

router = APIRouter(prefix="/v1/stream", tags=["stream"])


@router.get("/nodes")
async def stream_nodes(request: Request) -> StreamingResponse:
    """Server-Sent Events stream for node updates.

    Emits `node_update` events whenever heartbeat metrics are updated or when a node status changes.
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


@router.get("/jobs")
async def stream_jobs(request: Request) -> StreamingResponse:
    """Server-Sent Events stream for job progress updates.

    Emits `job_update` events on job/task state transitions.
    """

    async def generator():
        queue = await job_event_bus.subscribe()
        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: job_update\ndata: {event.model_dump_json()}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            await job_event_bus.unsubscribe(queue)

    return StreamingResponse(generator(), media_type="text/event-stream")
