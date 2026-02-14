from dataclasses import dataclass

from models import Node, RolePreference, TaskType


@dataclass(slots=True)
class EffectiveCapacity:
    effective_cpu_threads: float
    effective_ram_gb: float
    effective_vram_gb: float | None


def _task_requires_gpu(task_type: TaskType) -> bool:
    return task_type == TaskType.INFERENCE


def compute_effective_capacity(node: Node) -> EffectiveCapacity:
    cpu_threads = node.capabilities.cpu_threads or node.capabilities.cpu_cores or 0
    ram_total = node.capabilities.ram_total_gb or node.capabilities.ram_gb or 0.0
    vram_total = node.capabilities.vram_total_gb

    effective_cpu_threads = round(cpu_threads * (node.policy.cpu_cap_percent / 100.0), 3)
    effective_ram_gb = round(ram_total * (node.policy.ram_cap_percent / 100.0), 3)

    effective_vram_gb: float | None = None
    if vram_total is not None:
        gpu_cap = node.policy.gpu_cap_percent if node.policy.gpu_cap_percent is not None else 100
        effective_vram_gb = round(vram_total * (gpu_cap / 100.0), 3)

    return EffectiveCapacity(
        effective_cpu_threads=effective_cpu_threads,
        effective_ram_gb=effective_ram_gb,
        effective_vram_gb=effective_vram_gb,
    )


def evaluate_node_eligibility(node: Node, task_type: TaskType) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    if not node.policy.enabled:
        reasons.append("policy_disabled")
    if node.status.value != "ONLINE":
        reasons.append("node_not_online")
    if task_type not in node.policy.task_allowlist:
        reasons.append("task_not_allowed")

    if node.metrics.cpu_percent > node.policy.cpu_cap_percent:
        reasons.append("cpu_over_cap")
    if node.metrics.ram_percent > node.policy.ram_cap_percent:
        reasons.append("ram_over_cap")

    # Only apply GPU cap checks when a GPU signal exists for the node and task type.
    if _task_requires_gpu(task_type) and node.metrics.gpu_percent is not None:
        gpu_cap = node.policy.gpu_cap_percent if node.policy.gpu_cap_percent is not None else 100
        if node.metrics.gpu_percent > gpu_cap:
            reasons.append("gpu_over_cap")

    return (len(reasons) == 0, reasons)


def is_node_eligible(node: Node, task_type: TaskType) -> bool:
    eligible, _ = evaluate_node_eligibility(node, task_type)
    return eligible


def score_node(node: Node, task_type: TaskType) -> float:
    cpu_cap = max(node.policy.cpu_cap_percent, 1)
    ram_cap = max(node.policy.ram_cap_percent, 1)

    cpu_ratio = min(node.metrics.cpu_percent / cpu_cap, 2.0)
    ram_ratio = min(node.metrics.ram_percent / ram_cap, 2.0)

    score = 100.0 - ((cpu_ratio * 50.0) + (ram_ratio * 40.0))

    if task_type == TaskType.INFERENCE and node.capabilities.has_gpu:
        if node.policy.role_preference in (RolePreference.AUTO, RolePreference.PREFER_INFERENCE):
            score += 10.0

    if node.policy.role_preference == RolePreference.PREFER_INFERENCE and task_type == TaskType.INFERENCE:
        score += 15.0
    if node.policy.role_preference == RolePreference.PREFER_EMBEDDINGS and task_type == TaskType.EMBEDDINGS:
        score += 15.0
    if node.policy.role_preference == RolePreference.PREFER_PREPROCESS and task_type == TaskType.PREPROCESS:
        score += 15.0

    if node.metrics.gpu_percent is not None and task_type == TaskType.INFERENCE:
        gpu_cap = node.policy.gpu_cap_percent if node.policy.gpu_cap_percent is not None else 100
        gpu_cap = max(gpu_cap, 1)
        gpu_ratio = min(node.metrics.gpu_percent / gpu_cap, 2.0)
        score -= gpu_ratio * 10.0

    return round(score, 3)
