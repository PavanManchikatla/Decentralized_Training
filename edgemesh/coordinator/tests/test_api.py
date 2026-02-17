import importlib

import pytest
from fastapi.testclient import TestClient

SHARED_SECRET = "test-shared-secret"


@pytest.fixture()
def client(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    db_path = tmp_path / "api-test.db"
    monkeypatch.setenv("COORDINATOR_DB_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("NODE_STALE_SECONDS", "15")
    monkeypatch.setenv("EDGE_MESH_SHARED_SECRET", SHARED_SECRET)

    from coordinator_service import main as main_module

    main_module = importlib.reload(main_module)
    with TestClient(main_module.app) as test_client:
        yield test_client


def _agent_headers() -> dict[str, str]:
    return {"X-EdgeMesh-Secret": SHARED_SECRET}


def _register_agent_legacy(client: TestClient, agent_id: str = "agent-1") -> None:
    response = client.post(
        "/api/agents/register",
        headers=_agent_headers(),
        json={
            "agent_id": agent_id,
            "capabilities": ["inference", "gpu"],
            "metadata": {
                "display_name": "Agent One",
                "ip": "127.0.0.1",
                "port": 9001,
            },
        },
    )
    assert response.status_code == 201


def _heartbeat_agent_legacy(
    client: TestClient, agent_id: str = "agent-1", cpu_percent: float = 45.5
) -> None:
    response = client.post(
        f"/api/agents/{agent_id}/heartbeat",
        headers=_agent_headers(),
        json={
            "status": "healthy",
            "metrics": {
                "cpu_percent": cpu_percent,
                "ram_used_gb": 14.2,
                "ram_percent": 62.0,
                "running_jobs": 2,
            },
        },
    )
    assert response.status_code == 202


def _register_agent_v1(
    client: TestClient, node_id: str = "node-1", has_gpu: bool = True
) -> None:
    capabilities: dict[str, object] = {
        "cpu_cores": 8,
        "cpu_threads": 16,
        "ram_total_gb": 32,
        "os": "linux",
        "arch": "x86_64",
        "task_types": ["INFERENCE", "EMBEDDINGS", "INDEX", "TOKENIZE", "PREPROCESS"],
        "labels": ["inference"],
    }
    if has_gpu:
        capabilities.update(
            {
                "gpu_name": "NVIDIA L4",
                "vram_total_gb": 24,
                "labels": ["gpu", "inference"],
            }
        )

    response = client.post(
        "/v1/agent/register",
        headers=_agent_headers(),
        json={
            "node_id": node_id,
            "display_name": "Edge Node",
            "ip": "10.0.0.5",
            "port": 9100,
            "capabilities": capabilities,
        },
    )
    assert response.status_code == 201


def _heartbeat_agent_v1(
    client: TestClient, node_id: str = "node-1", cpu_percent: float = 34.0
) -> None:
    response = client.post(
        "/v1/agent/heartbeat",
        headers=_agent_headers(),
        json={
            "node_id": node_id,
            "metrics": {
                "cpu_percent": cpu_percent,
                "ram_used_gb": 7.8,
                "ram_percent": 51.2,
                "gpu_percent": 40.0,
                "vram_used_gb": 6.0,
                "running_jobs": 1,
            },
        },
    )
    assert response.status_code == 202


def test_health_check(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_agent_auth_rejects_missing_secret(client: TestClient) -> None:
    response = client.post(
        "/v1/agent/register",
        json={
            "node_id": "unauthorized-node",
            "display_name": "Unauthorized",
            "ip": "127.0.0.1",
            "port": 9000,
            "capabilities": {"cpu_cores": 2, "cpu_threads": 4, "ram_total_gb": 8},
        },
    )
    assert response.status_code == 401


def test_register_and_heartbeat_flow_legacy(client: TestClient) -> None:
    _register_agent_legacy(client)
    _heartbeat_agent_legacy(client)

    list_response = client.get("/api/agents")

    assert list_response.status_code == 200

    rows = list_response.json()
    assert len(rows) == 1
    assert rows[0]["agent_id"] == "agent-1"
    assert rows[0]["status"] == "online"
    assert rows[0]["is_stale"] is False


def test_v1_nodes_and_detail_with_history(client: TestClient) -> None:
    _register_agent_legacy(client)
    _heartbeat_agent_legacy(client)

    nodes_response = client.get("/v1/nodes")
    detail_response = client.get(
        "/v1/nodes/agent-1",
        params={"include_metrics_history": "true", "history_limit": 10},
    )

    assert nodes_response.status_code == 200
    nodes = nodes_response.json()
    assert len(nodes) == 1
    assert nodes[0]["identity"]["node_id"] == "agent-1"
    assert nodes[0]["policy"]["cpu_cap_percent"] == 100

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["node"]["identity"]["node_id"] == "agent-1"
    assert len(detail["metrics_history"]) >= 1


def test_update_node_policy(client: TestClient) -> None:
    _register_agent_legacy(client)

    response = client.put(
        "/v1/nodes/agent-1/policy",
        json={
            "enabled": True,
            "cpu_cap_percent": 80,
            "gpu_cap_percent": 70,
            "ram_cap_percent": 75,
            "task_allowlist": ["INFERENCE", "EMBEDDINGS"],
            "role_preference": "PREFER_INFERENCE",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["identity"]["node_id"] == "agent-1"
    assert payload["policy"]["cpu_cap_percent"] == 80
    assert payload["policy"]["role_preference"] == "PREFER_INFERENCE"


def test_v1_agent_register_and_heartbeat(client: TestClient) -> None:
    _register_agent_v1(client)
    _heartbeat_agent_v1(client)

    response = client.get("/v1/nodes")

    assert response.status_code == 200
    nodes = response.json()
    assert len(nodes) == 1
    assert nodes[0]["identity"]["node_id"] == "node-1"
    assert nodes[0]["capabilities"]["cpu_threads"] == 16
    assert nodes[0]["capabilities"]["gpu_name"] == "NVIDIA L4"
    assert nodes[0]["metrics"]["ram_used_gb"] == 7.8


def test_schedule_ineligible_with_low_cpu_cap(client: TestClient) -> None:
    _register_agent_v1(client, node_id="node-low-cap")
    _heartbeat_agent_v1(client, node_id="node-low-cap", cpu_percent=9.0)

    policy_response = client.put(
        "/v1/nodes/node-low-cap/policy",
        json={
            "enabled": True,
            "cpu_cap_percent": 1,
            "gpu_cap_percent": 100,
            "ram_cap_percent": 90,
            "task_allowlist": ["INFERENCE", "EMBEDDINGS", "PREPROCESS"],
            "role_preference": "AUTO",
        },
    )
    assert policy_response.status_code == 200

    schedule_response = client.post(
        "/v1/simulate/schedule", json={"task_type": "INFER"}
    )
    assert schedule_response.status_code == 200

    payload = schedule_response.json()
    assert payload["chosen_node_id"] is None
    assert payload["reason"] == "No eligible nodes found"
    assert len(payload["ranked_candidates"]) == 1
    assert payload["ranked_candidates"][0]["eligible"] is False
    assert "cpu_over_cap" in payload["ranked_candidates"][0]["reasons"]


def test_simulate_prefers_gpu_for_infer(client: TestClient) -> None:
    _register_agent_v1(client, node_id="gpu-node", has_gpu=True)
    _register_agent_v1(client, node_id="cpu-node", has_gpu=False)
    _heartbeat_agent_v1(client, node_id="gpu-node", cpu_percent=20.0)
    _heartbeat_agent_v1(client, node_id="cpu-node", cpu_percent=20.0)

    client.put(
        "/v1/nodes/gpu-node/policy",
        json={
            "enabled": True,
            "cpu_cap_percent": 100,
            "gpu_cap_percent": 100,
            "ram_cap_percent": 100,
            "task_allowlist": [
                "INFERENCE",
                "EMBEDDINGS",
                "INDEX",
                "TOKENIZE",
                "PREPROCESS",
            ],
            "role_preference": "AUTO",
        },
    )
    client.put(
        "/v1/nodes/cpu-node/policy",
        json={
            "enabled": True,
            "cpu_cap_percent": 100,
            "gpu_cap_percent": None,
            "ram_cap_percent": 100,
            "task_allowlist": [
                "INFERENCE",
                "EMBEDDINGS",
                "INDEX",
                "TOKENIZE",
                "PREPROCESS",
            ],
            "role_preference": "PREFER_EMBEDDINGS",
        },
    )

    infer_response = client.post("/v1/simulate/schedule", json={"task_type": "INFER"})
    assert infer_response.status_code == 200
    infer_payload = infer_response.json()
    assert infer_payload["chosen_node_id"] == "gpu-node"


def test_cluster_summary_updates_when_policy_changes(client: TestClient) -> None:
    _register_agent_v1(client, node_id="node-summary")
    _heartbeat_agent_v1(client, node_id="node-summary", cpu_percent=10.0)

    summary_before = client.get("/v1/cluster/summary")
    assert summary_before.status_code == 200
    before_payload = summary_before.json()
    assert before_payload["total_effective_cpu_threads"] == 16.0

    policy_response = client.put(
        "/v1/nodes/node-summary/policy",
        json={
            "enabled": True,
            "cpu_cap_percent": 50,
            "gpu_cap_percent": 100,
            "ram_cap_percent": 100,
            "task_allowlist": [
                "INFERENCE",
                "EMBEDDINGS",
                "INDEX",
                "TOKENIZE",
                "PREPROCESS",
            ],
            "role_preference": "AUTO",
        },
    )
    assert policy_response.status_code == 200

    summary_after = client.get("/v1/cluster/summary")
    assert summary_after.status_code == 200
    after_payload = summary_after.json()
    assert after_payload["total_effective_cpu_threads"] == 8.0


def test_jobs_crud_filters_and_transitions(client: TestClient) -> None:
    _register_agent_v1(client, node_id="jobs-node")
    _heartbeat_agent_v1(client, node_id="jobs-node", cpu_percent=18.0)

    created_embed = client.post(
        "/v1/jobs",
        json={"task_type": "EMBED", "payload_ref": "demo://payload/embed-01"},
    )
    assert created_embed.status_code == 201
    embed_job = created_embed.json()

    created_infer = client.post(
        "/v1/jobs",
        json={"task_type": "INFER", "payload_ref": "demo://payload/infer-01"},
    )
    assert created_infer.status_code == 201
    infer_job = created_infer.json()

    list_all = client.get("/v1/jobs")
    assert list_all.status_code == 200
    assert len(list_all.json()) == 2

    list_embed = client.get("/v1/jobs", params={"task_type": "EMBED"})
    assert list_embed.status_code == 200
    assert len(list_embed.json()) == 1
    assert list_embed.json()[0]["id"] == embed_job["id"]

    detail = client.get(f"/v1/jobs/{embed_job['id']}")
    assert detail.status_code == 200
    assert detail.json()["payload_ref"] == "demo://payload/embed-01"

    to_running = client.post(
        f"/v1/jobs/{embed_job['id']}/status", json={"status": "RUNNING"}
    )
    assert to_running.status_code == 200
    assert to_running.json()["status"] == "RUNNING"
    assert to_running.json()["attempts"] == 1

    to_completed = client.post(
        f"/v1/jobs/{embed_job['id']}/status", json={"status": "COMPLETED"}
    )
    assert to_completed.status_code == 200
    assert to_completed.json()["status"] == "COMPLETED"

    invalid_transition = client.post(
        f"/v1/jobs/{infer_job['id']}/status",
        json={"status": "COMPLETED"},
    )
    assert invalid_transition.status_code == 409


def test_demo_embed_burst_populates_jobs(client: TestClient) -> None:
    _register_agent_v1(client, node_id="demo-node")
    _heartbeat_agent_v1(client, node_id="demo-node", cpu_percent=12.0)

    response = client.post("/v1/demo/jobs/create-embed-burst", params={"count": 6})
    assert response.status_code == 200

    payload = response.json()
    assert payload["created_count"] == 6
    assert len(payload["jobs"]) == 6
    assert payload["assigned_count"] >= 1

    list_response = client.get("/v1/jobs")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 6


def test_tasks_pull_submit_and_job_completion(client: TestClient) -> None:
    _register_agent_v1(client, node_id="worker-a", has_gpu=False)
    _heartbeat_agent_v1(client, node_id="worker-a", cpu_percent=9.0)

    created = client.post(
        "/v1/jobs",
        json={
            "task_type": "EMBED",
            "payload_ref": "demo://phase15/job-1",
            "task_count": 2,
            "max_task_retries": 1,
        },
    )
    assert created.status_code == 201
    job_id = created.json()["id"]
    assert created.json()["total_tasks"] == 2

    pull_one = client.post(
        "/v1/tasks/pull",
        headers=_agent_headers(),
        json={"node_id": "worker-a"},
    )
    assert pull_one.status_code == 200
    task_one = pull_one.json()["task"]
    assert task_one is not None

    result_one = client.post(
        f"/v1/tasks/{task_one['id']}/result",
        headers=_agent_headers(),
        json={
            "node_id": "worker-a",
            "success": True,
            "output": {"items_processed": 1},
            "duration_ms": 120,
        },
    )
    assert result_one.status_code == 200

    pull_two = client.post(
        "/v1/tasks/pull",
        headers=_agent_headers(),
        json={"node_id": "worker-a"},
    )
    assert pull_two.status_code == 200
    task_two = pull_two.json()["task"]
    assert task_two is not None

    result_two = client.post(
        f"/v1/tasks/{task_two['id']}/result",
        headers=_agent_headers(),
        json={
            "node_id": "worker-a",
            "success": True,
            "output": {"items_processed": 1},
            "duration_ms": 160,
        },
    )
    assert result_two.status_code == 200

    job_detail = client.get(f"/v1/jobs/{job_id}")
    assert job_detail.status_code == 200
    payload = job_detail.json()
    assert payload["status"] == "COMPLETED"
    assert payload["completed_tasks"] == 2

    metrics = client.get("/v1/metrics/execution")
    assert metrics.status_code == 200
    metrics_payload = metrics.json()
    assert metrics_payload["success_results"] >= 2


def test_task_retry_and_reassignment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TASK_LEASE_SECONDS", "1")

    _register_agent_v1(client, node_id="worker-1", has_gpu=False)
    _register_agent_v1(client, node_id="worker-2", has_gpu=False)
    _heartbeat_agent_v1(client, node_id="worker-1", cpu_percent=8.0)
    _heartbeat_agent_v1(client, node_id="worker-2", cpu_percent=8.0)

    created = client.post(
        "/v1/jobs",
        json={
            "task_type": "TOKENIZE",
            "payload_ref": "demo://phase15/reassign",
            "task_count": 1,
            "max_task_retries": 1,
        },
    )
    assert created.status_code == 201
    job_id = created.json()["id"]

    first_pull = client.post(
        "/v1/tasks/pull",
        headers=_agent_headers(),
        json={"node_id": "worker-1"},
    )
    assert first_pull.status_code == 200
    first_task = first_pull.json()["task"]
    assert first_task is not None

    import time

    time.sleep(1.2)

    second_pull = client.post(
        "/v1/tasks/pull",
        headers=_agent_headers(),
        json={"node_id": "worker-2"},
    )
    assert second_pull.status_code == 200
    reassigned = second_pull.json()["task"]
    assert reassigned is not None
    assert reassigned["id"] == first_task["id"]
    assert reassigned["retries"] == 1

    failed_result = client.post(
        f"/v1/tasks/{reassigned['id']}/result",
        headers=_agent_headers(),
        json={
            "node_id": "worker-2",
            "success": False,
            "output": {"error": "simulated"},
            "duration_ms": 75,
        },
    )
    assert failed_result.status_code == 200

    job_detail = client.get(f"/v1/jobs/{job_id}")
    assert job_detail.status_code == 200
    assert job_detail.json()["failed_tasks"] == 1


def test_tasks_pull_requires_secret(client: TestClient) -> None:
    response = client.post("/v1/tasks/pull", json={"node_id": "node-missing-secret"})
    assert response.status_code == 401
