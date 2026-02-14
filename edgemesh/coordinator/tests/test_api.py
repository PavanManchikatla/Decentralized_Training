import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "api-test.db"
    monkeypatch.setenv("COORDINATOR_DB_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("NODE_STALE_SECONDS", "15")

    from coordinator_service import main as main_module

    main_module = importlib.reload(main_module)
    with TestClient(main_module.app) as test_client:
        yield test_client


def _register_agent_legacy(client: TestClient, agent_id: str = "agent-1") -> None:
    response = client.post(
        "/api/agents/register",
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


def _heartbeat_agent_legacy(client: TestClient, agent_id: str = "agent-1", cpu_percent: float = 45.5) -> None:
    response = client.post(
        f"/api/agents/{agent_id}/heartbeat",
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


def _register_agent_v1(client: TestClient, node_id: str = "node-1") -> None:
    response = client.post(
        "/v1/agent/register",
        json={
            "node_id": node_id,
            "display_name": "Edge Node",
            "ip": "10.0.0.5",
            "port": 9100,
            "capabilities": {
                "cpu_cores": 8,
                "cpu_threads": 16,
                "ram_total_gb": 32,
                "gpu_name": "NVIDIA L4",
                "vram_total_gb": 24,
                "os": "linux",
                "arch": "x86_64",
                "task_types": ["INFERENCE", "EMBEDDINGS"],
                "labels": ["gpu", "inference"],
            },
        },
    )
    assert response.status_code == 201


def _heartbeat_agent_v1(client: TestClient, node_id: str = "node-1", cpu_percent: float = 34.0) -> None:
    response = client.post(
        "/v1/agent/heartbeat",
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

    schedule_response = client.post("/v1/simulate/schedule", json={"task_type": "INFER"})
    assert schedule_response.status_code == 200

    payload = schedule_response.json()
    assert payload["chosen_node_id"] is None
    assert payload["reason"] == "No eligible nodes found"
    assert len(payload["ranked_candidates"]) == 1
    assert payload["ranked_candidates"][0]["eligible"] is False
    assert "cpu_over_cap" in payload["ranked_candidates"][0]["reasons"]


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
            "task_allowlist": ["INFERENCE", "EMBEDDINGS", "PREPROCESS"],
            "role_preference": "AUTO",
        },
    )
    assert policy_response.status_code == 200

    summary_after = client.get("/v1/cluster/summary")
    assert summary_after.status_code == 200
    after_payload = summary_after.json()
    assert after_payload["total_effective_cpu_threads"] == 8.0
