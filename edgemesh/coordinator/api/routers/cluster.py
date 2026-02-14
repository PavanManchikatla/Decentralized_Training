from fastapi import APIRouter

from api.schemas import ClusterSummaryResponse
from db import get_nodes
from models import NodeStatus
from scheduler import compute_effective_capacity

router = APIRouter(prefix="/v1/cluster", tags=["cluster"])


@router.get("/summary", response_model=ClusterSummaryResponse)
async def cluster_summary() -> ClusterSummaryResponse:
    """Return aggregated cluster capacity and utilization totals.

    Totals are backend-computed so clients can display summary metrics without duplicating
    scheduler math in the browser.
    """

    nodes = get_nodes()

    total_nodes = len(nodes)
    online_nodes = sum(1 for node in nodes if node.status == NodeStatus.ONLINE)
    offline_nodes = sum(1 for node in nodes if node.status == NodeStatus.OFFLINE)

    total_effective_cpu_threads = 0.0
    total_effective_ram_gb = 0.0
    total_effective_vram_gb = 0.0
    active_running_jobs_total = 0

    for node in nodes:
        active_running_jobs_total += node.metrics.running_jobs

        if not node.policy.enabled or node.status != NodeStatus.ONLINE:
            continue

        capacity = compute_effective_capacity(node)
        total_effective_cpu_threads += capacity.effective_cpu_threads
        total_effective_ram_gb += capacity.effective_ram_gb
        if capacity.effective_vram_gb is not None:
            total_effective_vram_gb += capacity.effective_vram_gb

    return ClusterSummaryResponse(
        total_nodes=total_nodes,
        online_nodes=online_nodes,
        offline_nodes=offline_nodes,
        total_effective_cpu_threads=round(total_effective_cpu_threads, 3),
        total_effective_ram_gb=round(total_effective_ram_gb, 3),
        total_effective_vram_gb=round(total_effective_vram_gb, 3),
        active_running_jobs_total=active_running_jobs_total,
    )
