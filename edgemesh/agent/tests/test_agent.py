from pathlib import Path

from agent_service.main import (
    _task_types_from_capabilities,
    build_heartbeat_payload,
    load_or_create_node_id,
)


def test_load_or_create_node_id_is_persistent(tmp_path: Path) -> None:
    file_path = tmp_path / "state" / "node_id.txt"

    first = load_or_create_node_id(file_path)
    second = load_or_create_node_id(file_path)

    assert first == second
    assert first.startswith("node-")


def test_task_types_prefer_gpu_for_inference() -> None:
    gpu_types = _task_types_from_capabilities({"gpu_name": "NVIDIA"})
    cpu_types = _task_types_from_capabilities({"gpu_name": None})

    assert "INFERENCE" in gpu_types
    assert "INFERENCE" not in cpu_types


def test_build_heartbeat_payload_shape() -> None:
    payload = build_heartbeat_payload("node-abc")

    assert payload["node_id"] == "node-abc"
    metrics = payload["metrics"]
    assert "cpu_percent" in metrics
    assert "ram_used_gb" in metrics
    assert "ram_percent" in metrics
    assert "running_jobs" in metrics


def test_execute_task_generates_embedding_shape() -> None:
    from agent_service.main import _execute_task

    result = _execute_task(
        {
            "id": "task-1",
            "type": "EMBEDDINGS",
            "payload": {"text": "hello world"},
        }
    )

    assert "embedding" in result
    assert isinstance(result["embedding"], list)
    assert result["dims"] == len(result["embedding"])
