from api.routers.agent import router as agent_router
from api.routers.cluster import router as cluster_router
from api.routers.health import router as health_router
from api.routers.jobs import router as jobs_router
from api.routers.metrics import router as metrics_router
from api.routers.nodes import router as nodes_router
from api.routers.simulate import router as simulate_router
from api.routers.stream import router as stream_router
from api.routers.tasks import router as tasks_router

__all__ = [
    "agent_router",
    "cluster_router",
    "health_router",
    "jobs_router",
    "metrics_router",
    "nodes_router",
    "simulate_router",
    "stream_router",
    "tasks_router",
]
