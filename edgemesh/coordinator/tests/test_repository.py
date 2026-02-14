from datetime import datetime, timedelta, timezone

from db.repository import CoordinatorRepository
from models import Job, JobStatus, NodeCapabilities, NodeMetrics, NodePolicy, NodeStatus, TaskType


def test_repository_node_crud(tmp_path) -> None:
    db_path = tmp_path / "repo-test.db"
    repo = CoordinatorRepository(f"sqlite:///{db_path}")

    repo.upsert_node_identity(
        node_id="node-1",
        display_name="Node One",
        ip="10.0.0.5",
        port=7001,
    )
    repo.upsert_node_capabilities(
        node_id="node-1",
        capabilities=NodeCapabilities(
            task_types=[TaskType.INFERENCE],
            labels=["gpu", "inference"],
            has_gpu=True,
            cpu_cores=8,
            ram_gb=32,
            gpu_name="RTX",
        ),
    )
    repo.update_node_metrics(
        node_id="node-1",
        metrics=NodeMetrics(
            cpu_percent=45,
            gpu_percent=55,
            ram_percent=65,
            running_jobs=2,
            heartbeat_ts=datetime.now(timezone.utc) - timedelta(seconds=120),
            extra={"uptime_seconds": 500.0},
        ),
    )
    repo.update_node_policy(
        node_id="node-1",
        policy=NodePolicy(
            enabled=True,
            cpu_cap_percent=85,
            gpu_cap_percent=75,
            ram_cap_percent=80,
            task_allowlist=[TaskType.INFERENCE],
        ),
    )

    node = repo.get_node("node-1")
    assert node is not None
    assert node.identity.display_name == "Node One"
    assert node.capabilities.has_gpu is True
    assert node.metrics.running_jobs == 2
    assert node.policy.cpu_cap_percent == 85
    assert node.status == NodeStatus.ONLINE

    nodes = repo.get_nodes()
    assert len(nodes) == 1

    stale_nodes = repo.mark_offline_if_stale_nodes(stale_seconds=60)
    assert len(stale_nodes) == 1
    assert stale_nodes[0].status == NodeStatus.OFFLINE

    stale_node = repo.get_node("node-1")
    assert stale_node is not None
    assert stale_node.status == NodeStatus.OFFLINE

    repo.close()


def test_repository_job_crud(tmp_path) -> None:
    db_path = tmp_path / "job-test.db"
    repo = CoordinatorRepository(f"sqlite:///{db_path}")

    created = repo.create_job(
        Job(
            id="job-1",
            type=TaskType.EMBEDDINGS,
            status=JobStatus.QUEUED,
            assigned_node_id=None,
        )
    )

    fetched = repo.get_job("job-1")

    assert created.id == "job-1"
    assert fetched is not None
    assert fetched.type == TaskType.EMBEDDINGS
    assert fetched.status == JobStatus.QUEUED

    repo.close()
