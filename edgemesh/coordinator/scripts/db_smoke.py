from db.repository import CoordinatorRepository
from models import NodeCapabilities, NodeMetrics, TaskType


def main() -> None:
    repo = CoordinatorRepository("sqlite:///./coordinator.db")

    repo.upsert_node_identity(
        node_id="smoke-node-1",
        display_name="Smoke Node",
        ip="127.0.0.1",
        port=9100,
    )
    repo.upsert_node_capabilities(
        node_id="smoke-node-1",
        capabilities=NodeCapabilities(
            task_types=[TaskType.INFERENCE],
            labels=["inference", "gpu"],
            has_gpu=True,
        ),
    )
    repo.update_node_metrics(
        node_id="smoke-node-1",
        metrics=NodeMetrics(
            cpu_percent=21.0,
            gpu_percent=35.0,
            ram_percent=42.0,
            running_jobs=1,
            extra={"uptime_seconds": 12.0},
        ),
    )

    node = repo.get_node("smoke-node-1")
    print(node.model_dump_json(indent=2) if node else "node not found")


if __name__ == "__main__":
    main()
