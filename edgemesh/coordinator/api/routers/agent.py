from fastapi import APIRouter, Body, status

from api.schemas import AgentHeartbeatV1Request, AgentRegisterV1Request
from api.services import heartbeat_agent_v1, register_agent_v1
from models import Node, NodeUpdateEvent, TaskType

router = APIRouter(prefix="/v1/agent", tags=["agent"])


@router.post("/register", response_model=Node, status_code=status.HTTP_201_CREATED)
async def register_agent(
    payload: AgentRegisterV1Request = Body(
        ...,
        examples={
            "default": {
                "summary": "Agent register payload",
                "value": {
                    "node_id": "node-123",
                    "display_name": "edge-host-01",
                    "ip": "10.0.0.21",
                    "port": 9100,
                    "capabilities": {
                        "cpu_cores": 8,
                        "cpu_threads": 16,
                        "ram_total_gb": 64,
                        "gpu_name": "NVIDIA L4",
                        "vram_total_gb": 24,
                        "os": "linux",
                        "arch": "x86_64",
                        "task_types": [TaskType.INFERENCE.value, TaskType.EMBEDDINGS.value],
                        "labels": ["gpu", "inference"],
                    },
                },
            }
        },
    )
) -> Node:
    """Register or update an agent identity and capabilities.

    Upserts node identity and capability metadata in SQLite and returns the updated node.
    """

    return register_agent_v1(payload)


@router.post("/heartbeat", response_model=NodeUpdateEvent, status_code=status.HTTP_202_ACCEPTED)
async def post_heartbeat(
    payload: AgentHeartbeatV1Request = Body(
        ...,
        examples={
            "default": {
                "summary": "Agent heartbeat payload",
                "value": {
                    "node_id": "node-123",
                    "metrics": {
                        "cpu_percent": 34.2,
                        "ram_used_gb": 12.1,
                        "ram_percent": 47.9,
                        "gpu_percent": 55.0,
                        "vram_used_gb": 8.6,
                        "running_jobs": 1,
                    },
                },
            }
        },
    )
) -> NodeUpdateEvent:
    """Accept a node heartbeat and broadcast SSE node_update event.

    On success this updates node metrics and status, appends metrics history in memory,
    and emits a `node_update` event on `/v1/stream/nodes`.
    """

    return await heartbeat_agent_v1(payload)
