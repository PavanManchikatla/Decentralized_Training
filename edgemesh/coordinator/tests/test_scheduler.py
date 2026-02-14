from models import (
    Node,
    NodeCapabilities,
    NodeIdentity,
    NodeMetrics,
    NodePolicy,
    NodeStatus,
    RolePreference,
    TaskType,
)
from scheduler import compute_effective_capacity, is_node_eligible


def _build_node() -> Node:
    return Node(
        identity=NodeIdentity(node_id="n1", display_name="Node 1", ip="127.0.0.1", port=9100),
        capabilities=NodeCapabilities(
            task_types=[TaskType.INFERENCE, TaskType.EMBEDDINGS],
            labels=["gpu"],
            has_gpu=True,
            cpu_cores=8,
            cpu_threads=16,
            ram_total_gb=32,
            vram_total_gb=24,
            gpu_name="NVIDIA",
            os="linux",
            arch="x86_64",
        ),
        metrics=NodeMetrics(
            cpu_percent=20,
            ram_used_gb=10,
            ram_percent=30,
            gpu_percent=40,
            vram_used_gb=5,
            running_jobs=1,
        ),
        policy=NodePolicy(
            enabled=True,
            cpu_cap_percent=50,
            gpu_cap_percent=75,
            ram_cap_percent=80,
            task_allowlist=[TaskType.INFERENCE, TaskType.EMBEDDINGS],
            role_preference=RolePreference.PREFER_INFERENCE,
        ),
        status=NodeStatus.ONLINE,
    )


def test_compute_effective_capacity() -> None:
    node = _build_node()

    cap = compute_effective_capacity(node)

    assert cap.effective_cpu_threads == 8.0
    assert cap.effective_ram_gb == 25.6
    assert cap.effective_vram_gb == 18.0


def test_is_node_eligible() -> None:
    node = _build_node()

    assert is_node_eligible(node, TaskType.INFERENCE) is True


def test_is_node_ineligible_when_cpu_over_cap() -> None:
    node = _build_node()
    node.metrics.cpu_percent = 60

    assert is_node_eligible(node, TaskType.INFERENCE) is False
