import asyncio
import logging
from contextlib import suppress
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from api.auth import require_agent_secret
from api.routers import (
    agent_router,
    cluster_router,
    health_router,
    jobs_router,
    metrics_router,
    nodes_router,
    simulate_router,
    stream_router,
    tasks_router,
)
from api.services import (
    heartbeat_agent_v1,
    register_agent_v1,
    to_v1_heartbeat_from_legacy,
    to_v1_register_from_legacy,
)
from api.tasks import stale_node_monitor, stale_task_monitor
from coordinator_service.logging_config import configure_logging
from coordinator_service.models import AgentRegisterRequest, AgentView, HeartbeatRequest
from coordinator_service.settings import Settings
from db import get_nodes, init_repository, mark_offline_if_stale
from models import NodeStatus

load_dotenv()
settings = Settings.from_env()
configure_logging(settings.log_level)
logger = logging.getLogger("coordinator")

app = FastAPI(title="edgemesh coordinator", version="0.2.0")
_stale_monitor_task: asyncio.Task[None] | None = None
_stale_task_monitor_task: asyncio.Task[None] | None = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(nodes_router)
app.include_router(stream_router)
app.include_router(agent_router)
app.include_router(tasks_router)
app.include_router(cluster_router)
app.include_router(metrics_router)
app.include_router(simulate_router)
app.include_router(jobs_router)


@app.on_event("startup")
async def startup() -> None:
    global _stale_monitor_task, _stale_task_monitor_task
    init_repository(settings.db_url)
    _stale_monitor_task = asyncio.create_task(
        stale_node_monitor(settings.node_stale_seconds)
    )
    _stale_task_monitor_task = asyncio.create_task(
        stale_task_monitor(settings.task_recovery_interval_seconds)
    )
    logger.info(
        "repository_initialized",
        extra={
            "db_url": settings.db_url,
            "node_stale_seconds": settings.node_stale_seconds,
            "offline_scan_interval_seconds": 5,
            "task_lease_seconds": settings.task_lease_seconds,
            "task_recovery_interval_seconds": settings.task_recovery_interval_seconds,
            "agent_secret_enabled": bool(settings.edge_mesh_shared_secret),
        },
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    global _stale_monitor_task, _stale_task_monitor_task

    if _stale_monitor_task is not None:
        _stale_monitor_task.cancel()
        with suppress(asyncio.CancelledError):
            await _stale_monitor_task
        _stale_monitor_task = None

    if _stale_task_monitor_task is not None:
        _stale_task_monitor_task.cancel()
        with suppress(asyncio.CancelledError):
            await _stale_task_monitor_task
        _stale_task_monitor_task = None


@app.post("/api/agents/register", status_code=status.HTTP_201_CREATED)
async def register_agent_legacy(
    payload: AgentRegisterRequest,
    _: None = Depends(require_agent_secret),
) -> dict[str, bool]:
    v1_payload = to_v1_register_from_legacy(payload)
    register_agent_v1(v1_payload)

    logger.info(
        "agent_registered",
        extra={
            "node_id": v1_payload.node_id,
            "capabilities": v1_payload.capabilities.labels,
        },
    )
    return {"ok": True}


@app.post("/api/agents/{agent_id}/heartbeat", status_code=status.HTTP_202_ACCEPTED)
async def post_heartbeat_legacy(
    agent_id: str,
    payload: HeartbeatRequest,
    _: None = Depends(require_agent_secret),
) -> dict[str, bool]:
    v1_payload = to_v1_heartbeat_from_legacy(agent_id=agent_id, payload=payload)
    await heartbeat_agent_v1(v1_payload)

    logger.info("heartbeat_received", extra={"node_id": v1_payload.node_id})
    return {"ok": True}


@app.get("/api/agents", response_model=list[AgentView])
async def list_agents_legacy() -> list[AgentView]:
    mark_offline_if_stale(settings.node_stale_seconds)
    nodes = get_nodes()

    response: list[AgentView] = []
    for node in nodes:
        capability_labels = list(node.capabilities.labels)
        for task_type in node.capabilities.task_types:
            value = task_type.value.lower()
            if value not in capability_labels:
                capability_labels.append(value)

        is_stale = node.status == NodeStatus.OFFLINE
        response.append(
            AgentView(
                agent_id=node.identity.node_id,
                capabilities=capability_labels,
                metadata={
                    "display_name": node.identity.display_name,
                    "ip": node.identity.ip,
                    "port": node.identity.port,
                    "policy_enabled": node.policy.enabled,
                },
                status=node.status.value.lower(),
                metrics=node.metrics.extra,
                last_seen=node.last_seen,
                is_stale=is_stale,
            )
        )

    return response


dist_dir = Path(__file__).resolve().parents[3] / "ui" / "dist"
if dist_dir.exists():
    app.mount("/", StaticFiles(directory=dist_dir, html=True), name="ui")
else:

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def root() -> str:
        return """
        <html>
          <head><title>edgemesh coordinator</title></head>
          <body>
            <h1>edgemesh coordinator</h1>
            <p>UI build not found. Run <code>cd ui && npm run build</code> to host UI here.</p>
            <p>For development, run <code>make ui-dev</code> and open http://localhost:5173.</p>
          </body>
        </html>
        """


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "coordinator_service.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
