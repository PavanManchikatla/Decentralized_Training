import asyncio
import hashlib
import logging
import platform
import shutil
import socket
import subprocess
import time
import uuid
from dataclasses import asdict
from pathlib import Path

import httpx
import psutil
from dotenv import load_dotenv

from agent_service.logging_config import configure_logging
from agent_service.settings import Settings

load_dotenv()
settings = Settings.from_env()
configure_logging(settings.log_level)
logger = logging.getLogger("agent")


def load_or_create_node_id(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value

    node_id = f"node-{uuid.uuid4().hex[:12]}"
    path.write_text(f"{node_id}\n", encoding="utf-8")
    return node_id


def detect_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if ip:
                return ip
        except OSError:
            pass
    return "127.0.0.1"


def _run_nvidia_query(fields: str) -> list[str] | None:
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi is None:
        return None

    try:
        result = subprocess.run(
            [
                nvidia_smi,
                f"--query-gpu={fields}",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    rows = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    if not rows:
        return None

    return [item.strip() for item in rows[0].split(",")]


def detect_gpu_capabilities() -> tuple[str | None, float | None]:
    row = _run_nvidia_query("name,memory.total")
    if row is None or len(row) < 2:
        return (None, None)

    gpu_name = row[0] or None
    try:
        vram_total_gb = round(float(row[1]) / 1024.0, 3)
    except ValueError:
        vram_total_gb = None

    return (gpu_name, vram_total_gb)


def detect_gpu_metrics() -> tuple[float | None, float | None]:
    row = _run_nvidia_query("utilization.gpu,memory.used")
    if row is None or len(row) < 2:
        return (None, None)

    try:
        gpu_percent = float(row[0])
    except ValueError:
        gpu_percent = None

    try:
        vram_used_gb = round(float(row[1]) / 1024.0, 3)
    except ValueError:
        vram_used_gb = None

    return (gpu_percent, vram_used_gb)


def detect_capabilities() -> dict[str, object]:
    cpu_cores = psutil.cpu_count(logical=False)
    cpu_threads = psutil.cpu_count(logical=True)
    ram_total_gb = round(psutil.virtual_memory().total / (1024**3), 3)
    gpu_name, vram_total_gb = detect_gpu_capabilities()

    return {
        "cpu_cores": cpu_cores,
        "cpu_threads": cpu_threads,
        "ram_total_gb": ram_total_gb,
        "gpu_name": gpu_name,
        "vram_total_gb": vram_total_gb,
        "os": platform.system().lower(),
        "arch": platform.machine().lower(),
        "labels": ["gpu"] if gpu_name else ["cpu"],
    }


def collect_metrics(running_jobs: int = 0) -> dict[str, float | int | None]:
    memory = psutil.virtual_memory()
    gpu_percent, vram_used_gb = detect_gpu_metrics()

    metrics: dict[str, float | int | None] = {
        "cpu_percent": float(psutil.cpu_percent(interval=None)),
        "ram_used_gb": round(memory.used / (1024**3), 3),
        "ram_percent": float(memory.percent),
        "gpu_percent": gpu_percent,
        "vram_used_gb": vram_used_gb,
        "running_jobs": running_jobs,
    }
    return metrics


def _task_types_from_capabilities(capabilities: dict[str, object]) -> list[str]:
    has_gpu = bool(capabilities.get("gpu_name"))
    if has_gpu:
        return ["INFERENCE", "EMBEDDINGS", "INDEX", "TOKENIZE", "PREPROCESS"]
    return ["EMBEDDINGS", "INDEX", "TOKENIZE", "PREPROCESS"]


def build_register_payload(node_id: str) -> dict[str, object]:
    capabilities = detect_capabilities()
    capabilities["task_types"] = _task_types_from_capabilities(capabilities)

    return {
        "node_id": node_id,
        "display_name": settings.display_name,
        "ip": detect_ip(),
        "port": settings.agent_port,
        "capabilities": capabilities,
    }


def build_heartbeat_payload(node_id: str, running_jobs: int = 0) -> dict[str, object]:
    return {
        "node_id": node_id,
        "metrics": collect_metrics(running_jobs=running_jobs),
    }


def _agent_headers() -> dict[str, str]:
    if not settings.edge_mesh_shared_secret:
        return {}
    return {"X-EdgeMesh-Secret": settings.edge_mesh_shared_secret}


def _payload_text(payload: dict[str, object]) -> str:
    for key in ("text", "item", "payload_ref"):
        value = payload.get(key)
        if value is not None:
            return str(value)
    return ""


def _execute_task(task: dict[str, object]) -> dict[str, object]:
    task_type = str(task.get("type", "")).upper()
    payload = task.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    text = _payload_text(payload)

    if task_type == "EMBEDDINGS":
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        vector = [
            int(digest[index : index + 4], 16) / 65535.0 for index in range(0, 32, 4)
        ]
        return {"embedding": vector, "dims": len(vector), "source": text[:64]}

    if task_type == "TOKENIZE":
        tokens = [token for token in text.strip().split() if token]
        return {"tokens": tokens[:256], "count": len(tokens)}

    if task_type == "PREPROCESS":
        cleaned = " ".join(text.strip().lower().split())
        return {"cleaned_text": cleaned, "length": len(cleaned)}

    if task_type == "INDEX":
        doc_id = hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()
        return {"document_id": doc_id, "length": len(text)}

    if task_type == "INFERENCE":
        label = "LONG" if len(text) > 120 else "SHORT"
        return {"label": label, "score": min(len(text) / 200.0, 1.0)}

    return {"message": "Unknown task type", "task_type": task_type}


async def register(client: httpx.AsyncClient, node_id: str) -> None:
    response = await client.post(
        "/v1/agent/register", json=build_register_payload(node_id)
    )
    response.raise_for_status()


async def send_heartbeat(
    client: httpx.AsyncClient, node_id: str, running_jobs: int
) -> None:
    response = await client.post(
        "/v1/agent/heartbeat",
        json=build_heartbeat_payload(node_id, running_jobs=running_jobs),
    )
    response.raise_for_status()


async def pull_task(
    client: httpx.AsyncClient, node_id: str
) -> dict[str, object] | None:
    response = await client.post("/v1/tasks/pull", json={"node_id": node_id})
    response.raise_for_status()

    payload = response.json()
    task = payload.get("task")
    if isinstance(task, dict):
        return task
    return None


async def submit_task_result(
    client: httpx.AsyncClient,
    task_id: str,
    node_id: str,
    success: bool,
    output: dict[str, object] | None,
    duration_ms: int,
) -> None:
    response = await client.post(
        f"/v1/tasks/{task_id}/result",
        json={
            "node_id": node_id,
            "success": success,
            "output": output,
            "duration_ms": duration_ms,
        },
    )
    response.raise_for_status()


async def run_agent() -> None:
    node_id = load_or_create_node_id(settings.state_file)
    logger.info(
        "agent_starting", extra={"node_id": node_id, "settings": asdict(settings)}
    )

    retry_delay = 1.0
    running_jobs = 0
    next_heartbeat_at = 0.0

    async with httpx.AsyncClient(
        base_url=settings.coordinator_url,
        timeout=20.0,
        headers=_agent_headers(),
    ) as client:
        while True:
            try:
                await register(client=client, node_id=node_id)
                logger.info("agent_registered", extra={"node_id": node_id})
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "agent_register_failed",
                    extra={
                        "node_id": node_id,
                        "error": str(exc),
                        "retry_delay_seconds": retry_delay,
                    },
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30.0)

        retry_delay = 1.0
        next_heartbeat_at = time.monotonic()

        while True:
            try:
                now = time.monotonic()
                if now >= next_heartbeat_at:
                    await send_heartbeat(
                        client=client,
                        node_id=node_id,
                        running_jobs=running_jobs,
                    )
                    logger.info(
                        "heartbeat_sent",
                        extra={"node_id": node_id, "running_jobs": running_jobs},
                    )
                    next_heartbeat_at = now + settings.heartbeat_seconds

                task = await pull_task(client=client, node_id=node_id)
                if task is None:
                    await asyncio.sleep(settings.task_poll_seconds)
                    continue

                task_id = str(task.get("id", ""))
                if not task_id:
                    await asyncio.sleep(settings.task_poll_seconds)
                    continue

                running_jobs += 1
                started = time.perf_counter()
                success = True
                output: dict[str, object] | None = None

                try:
                    output = _execute_task(task)
                except Exception as exc:  # noqa: BLE001
                    success = False
                    output = {"error": str(exc)}

                duration_ms = int((time.perf_counter() - started) * 1000)
                await submit_task_result(
                    client=client,
                    task_id=task_id,
                    node_id=node_id,
                    success=success,
                    output=output,
                    duration_ms=duration_ms,
                )
                logger.info(
                    "task_processed",
                    extra={
                        "node_id": node_id,
                        "task_id": task_id,
                        "success": success,
                        "duration_ms": duration_ms,
                    },
                )
                running_jobs = max(running_jobs - 1, 0)
                retry_delay = 1.0
            except Exception as exc:  # noqa: BLE001
                running_jobs = max(running_jobs - 1, 0)
                logger.warning(
                    "agent_cycle_failed",
                    extra={
                        "node_id": node_id,
                        "error": str(exc),
                        "retry_delay_seconds": retry_delay,
                    },
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30.0)


def main() -> None:
    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        logger.info("agent_shutdown")


if __name__ == "__main__":
    main()
