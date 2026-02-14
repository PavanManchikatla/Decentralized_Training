from coordinator_service.models import AgentRegisterRequest, HeartbeatRequest
from api.schemas import (
    AgentCapabilitiesPayload,
    AgentHeartbeatMetricsPayload,
    AgentHeartbeatV1Request,
    AgentRegisterV1Request,
)
from api.state import metrics_history_buffer, node_event_bus
from db import update_node_metrics, upsert_node_capabilities, upsert_node_identity
from models import Node, NodeCapabilities, NodeMetrics, NodeUpdateEvent, TaskType


def _parse_int(value: object, default: int = 0) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return default


def _parse_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _extract_task_types(labels: list[str]) -> list[TaskType]:
    mapping = {
        "infer": TaskType.INFERENCE,
        "inference": TaskType.INFERENCE,
        "embed": TaskType.EMBEDDINGS,
        "embedding": TaskType.EMBEDDINGS,
        "embeddings": TaskType.EMBEDDINGS,
        "preprocess": TaskType.PREPROCESS,
        "preprocessing": TaskType.PREPROCESS,
    }

    task_types: list[TaskType] = []
    for label in labels:
        task_type = mapping.get(label.strip().lower())
        if task_type is not None and task_type not in task_types:
            task_types.append(task_type)

    return task_types


def _normalize_task_types(task_types: list[TaskType], labels: list[str]) -> list[TaskType]:
    normalized: list[TaskType] = []

    for task_type in task_types:
        if task_type not in normalized:
            normalized.append(task_type)

    if not normalized:
        normalized = _extract_task_types(labels)

    if not normalized:
        normalized = list(TaskType)

    return normalized


def _build_node_capabilities(payload: AgentCapabilitiesPayload) -> NodeCapabilities:
    task_types = _normalize_task_types(payload.task_types, payload.labels)

    has_gpu = payload.gpu_name is not None or payload.vram_total_gb is not None
    return NodeCapabilities(
        task_types=task_types,
        labels=payload.labels,
        has_gpu=has_gpu,
        cpu_cores=payload.cpu_cores,
        cpu_threads=payload.cpu_threads,
        ram_total_gb=payload.ram_total_gb,
        gpu_name=payload.gpu_name,
        vram_total_gb=payload.vram_total_gb,
        os=payload.os,
        arch=payload.arch,
    )


def register_agent_v1(payload: AgentRegisterV1Request) -> Node:
    upsert_node_identity(
        node_id=payload.node_id,
        display_name=payload.display_name,
        ip=payload.ip,
        port=payload.port,
    )
    return upsert_node_capabilities(
        node_id=payload.node_id,
        capabilities=_build_node_capabilities(payload.capabilities),
    )


async def heartbeat_agent_v1(payload: AgentHeartbeatV1Request) -> NodeUpdateEvent:
    metrics = NodeMetrics(
        cpu_percent=payload.metrics.cpu_percent,
        ram_used_gb=payload.metrics.ram_used_gb,
        ram_percent=payload.metrics.ram_percent,
        gpu_percent=payload.metrics.gpu_percent,
        vram_used_gb=payload.metrics.vram_used_gb,
        running_jobs=payload.metrics.running_jobs,
        extra=payload.metrics.model_dump(mode="json", exclude_none=True),
    )

    node = update_node_metrics(node_id=payload.node_id, metrics=metrics)
    metrics_history_buffer.append(payload.node_id, node.metrics)

    event = NodeUpdateEvent(
        node_id=node.identity.node_id,
        status=node.status,
        metrics=node.metrics,
        updated_at=node.updated_at,
    )
    await node_event_bus.publish(event)
    return event


def to_v1_register_from_legacy(payload: AgentRegisterRequest) -> AgentRegisterV1Request:
    metadata = payload.metadata

    return AgentRegisterV1Request(
        node_id=payload.agent_id,
        display_name=str(metadata.get("display_name") or payload.agent_id),
        ip=str(metadata.get("ip") or "0.0.0.0"),
        port=_parse_int(metadata.get("port", 0)),
        capabilities=AgentCapabilitiesPayload(
            cpu_cores=_parse_int(metadata.get("cpu_cores"), 0) or None,
            cpu_threads=_parse_int(metadata.get("cpu_threads"), 0) or None,
            ram_total_gb=_parse_float(metadata.get("ram_total_gb"), 0.0) or None,
            gpu_name=(str(metadata.get("gpu_name")) if metadata.get("gpu_name") else None),
            vram_total_gb=_parse_float(metadata.get("vram_total_gb"), 0.0) or None,
            os=(str(metadata.get("os")) if metadata.get("os") else None),
            arch=(str(metadata.get("arch")) if metadata.get("arch") else None),
            labels=payload.capabilities,
            task_types=_extract_task_types(payload.capabilities),
        ),
    )


def to_v1_heartbeat_from_legacy(agent_id: str, payload: HeartbeatRequest) -> AgentHeartbeatV1Request:
    metrics = payload.metrics

    return AgentHeartbeatV1Request(
        node_id=agent_id,
        metrics=AgentHeartbeatMetricsPayload(
            cpu_percent=float(metrics.get("cpu_percent", 0.0)),
            ram_used_gb=float(metrics.get("ram_used_gb", 0.0)),
            ram_percent=float(metrics.get("ram_percent", 0.0)),
            gpu_percent=float(metrics["gpu_percent"]) if "gpu_percent" in metrics else None,
            vram_used_gb=float(metrics["vram_used_gb"]) if "vram_used_gb" in metrics else None,
            running_jobs=int(metrics.get("running_jobs", 0.0)),
        ),
    )
