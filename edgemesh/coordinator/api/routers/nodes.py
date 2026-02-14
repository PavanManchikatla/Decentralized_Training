from fastapi import APIRouter, Body, HTTPException, Query

from db import get_node, get_nodes, update_node_policy
from models import Node, NodeDetail, NodePolicy, TaskType
from api.state import metrics_history_buffer

router = APIRouter(prefix="/v1/nodes", tags=["nodes"])


@router.get("", response_model=list[Node])
async def list_nodes() -> list[Node]:
    """List all known nodes.

    Returns each node with identity, capabilities, latest metrics, policy, and status.

    Example response item:
    {
      "identity": {"node_id": "node-1", "display_name": "Node One", "ip": "10.0.0.5", "port": 7001},
      "capabilities": {"task_types": ["INFERENCE"], "labels": ["gpu", "inference"], "has_gpu": true},
      "metrics": {"cpu_percent": 31.5, "gpu_percent": 42.0, "ram_percent": 58.0, "running_jobs": 2},
      "policy": {
        "enabled": true,
        "cpu_cap_percent": 90,
        "gpu_cap_percent": 80,
        "ram_cap_percent": 85,
        "task_allowlist": ["INFERENCE", "EMBEDDINGS"],
        "role_preference": "PREFER_INFERENCE"
      },
      "status": "ONLINE"
    }
    """

    return get_nodes()


@router.get("/{node_id}", response_model=NodeDetail)
async def get_node_detail(
    node_id: str,
    include_metrics_history: bool = Query(default=False),
    history_limit: int = Query(default=20, ge=1, le=500),
) -> NodeDetail:
    """Get a single node, with optional in-memory metrics history.

    Query params:
    - include_metrics_history: include recent samples when true.
    - history_limit: max samples to return when history is included.
    """

    node = get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

    history = metrics_history_buffer.get(node_id, history_limit) if include_metrics_history else None
    return NodeDetail(node=node, metrics_history=history)


@router.put("/{node_id}/policy", response_model=Node)
async def put_node_policy(
    node_id: str,
    policy: NodePolicy = Body(
        ...,
        examples={
            "default": {
                "summary": "Inference heavy node policy",
                "value": {
                    "enabled": True,
                    "cpu_cap_percent": 85,
                    "gpu_cap_percent": 90,
                    "ram_cap_percent": 80,
                    "task_allowlist": [TaskType.INFERENCE.value, TaskType.EMBEDDINGS.value],
                    "role_preference": "PREFER_INFERENCE",
                },
            }
        },
    ),
) -> Node:
    """Update node policy.

    Percent fields are validated in [0..100] by Pydantic schema constraints.
    Returns the updated node object.
    """

    return update_node_policy(node_id=node_id, policy=policy)
