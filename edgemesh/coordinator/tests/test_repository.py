from datetime import datetime, timedelta, timezone

from db.repository import CoordinatorRepository
from models import (
    Job,
    JobStatus,
    NodeCapabilities,
    NodeMetrics,
    NodePolicy,
    NodeStatus,
    TaskResult,
    TaskStatus,
    TaskType,
)


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


def test_repository_job_crud_and_transitions(tmp_path) -> None:
    db_path = tmp_path / "job-test.db"
    repo = CoordinatorRepository(f"sqlite:///{db_path}")

    created = repo.create_job(
        Job(
            id="job-1",
            type=TaskType.EMBEDDINGS,
            status=JobStatus.QUEUED,
            payload_ref="demo://payload/1",
        )
    )

    fetched = repo.get_job("job-1")

    assert created.id == "job-1"
    assert fetched is not None
    assert fetched.type == TaskType.EMBEDDINGS
    assert fetched.status == JobStatus.QUEUED
    assert fetched.payload_ref == "demo://payload/1"
    assert fetched.attempts == 0

    running = repo.transition_job_status("job-1", JobStatus.RUNNING)
    assert running.status == JobStatus.RUNNING
    assert running.attempts == 1
    assert running.started_at is not None

    completed = repo.transition_job_status("job-1", JobStatus.COMPLETED)
    assert completed.status == JobStatus.COMPLETED
    assert completed.completed_at is not None

    rows = repo.list_jobs(status=JobStatus.COMPLETED)
    assert len(rows) == 1
    assert rows[0].id == "job-1"

    repo.close()


def test_repository_task_lifecycle_and_metrics(tmp_path) -> None:
    db_path = tmp_path / "task-test.db"
    repo = CoordinatorRepository(f"sqlite:///{db_path}")

    repo.upsert_node_identity(
        node_id="worker-1",
        display_name="Worker 1",
        ip="127.0.0.1",
        port=9100,
    )
    repo.upsert_node_capabilities(
        node_id="worker-1",
        capabilities=NodeCapabilities(
            task_types=[TaskType.EMBEDDINGS, TaskType.TOKENIZE],
            labels=["cpu"],
            has_gpu=False,
            cpu_threads=8,
            ram_total_gb=16,
        ),
    )
    repo.update_node_metrics(
        node_id="worker-1",
        metrics=NodeMetrics(cpu_percent=10, ram_percent=20, running_jobs=0),
    )

    job = repo.create_job(
        Job(
            id="job-task-1",
            type=TaskType.EMBEDDINGS,
            payload_ref="demo://repo-task",
        )
    )

    tasks = repo.create_tasks(
        job_id=job.id,
        task_type=TaskType.EMBEDDINGS,
        payloads=[{"text": "a"}, {"text": "b"}],
        max_retries=1,
    )
    assert len(tasks) == 2

    pulled = repo.pull_task_for_node("worker-1", lease_seconds=30)
    assert pulled is not None

    task_after, job_after = repo.submit_task_result(
        TaskResult(
            task_id=pulled.id,
            node_id="worker-1",
            success=True,
            output={"ok": True},
            duration_ms=123,
        )
    )
    assert task_after.status == TaskStatus.COMPLETED
    assert job_after.completed_tasks == 1

    metrics = repo.get_execution_metrics()
    assert metrics["success_results"] >= 1

    repo.close()
