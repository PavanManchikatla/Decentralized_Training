import asyncio
import logging
import platform
import shutil
import socket
import subprocess
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


def collect_metrics() -> dict[str, float | int | None]:
    memory = psutil.virtual_memory()
    gpu_percent, vram_used_gb = detect_gpu_metrics()

    metrics: dict[str, float | int | None] = {
        "cpu_percent": float(psutil.cpu_percent(interval=None)),
        "ram_used_gb": round(memory.used / (1024**3), 3),
        "ram_percent": float(memory.percent),
        "gpu_percent": gpu_percent,
        "vram_used_gb": vram_used_gb,
        "running_jobs": 0,
    }
    return metrics


def _task_types_from_capabilities(capabilities: dict[str, object]) -> list[str]:
    has_gpu = bool(capabilities.get("gpu_name"))
    if has_gpu:
        return ["INFERENCE", "EMBEDDINGS", "PREPROCESS"]
    return ["EMBEDDINGS", "PREPROCESS"]


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


def build_heartbeat_payload(node_id: str) -> dict[str, object]:
    return {
        "node_id": node_id,
        "metrics": collect_metrics(),
    }


async def register(client: httpx.AsyncClient, node_id: str) -> None:
    response = await client.post("/v1/agent/register", json=build_register_payload(node_id))
    response.raise_for_status()


async def send_heartbeat(client: httpx.AsyncClient, node_id: str) -> None:
    response = await client.post("/v1/agent/heartbeat", json=build_heartbeat_payload(node_id))
    response.raise_for_status()


async def run_agent() -> None:
    node_id = load_or_create_node_id(settings.state_file)
    logger.info("agent_starting", extra={"node_id": node_id, "settings": asdict(settings)})

    registered = False
    retry_delay = 1.0

    async with httpx.AsyncClient(base_url=settings.coordinator_url, timeout=10.0) as client:
        while True:
            try:
                if not registered:
                    await register(client=client, node_id=node_id)
                    registered = True
                    retry_delay = 1.0
                    logger.info("agent_registered", extra={"node_id": node_id})

                await send_heartbeat(client=client, node_id=node_id)
                logger.info("heartbeat_sent", extra={"node_id": node_id})
                await asyncio.sleep(settings.heartbeat_seconds)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "agent_cycle_failed",
                    extra={"node_id": node_id, "error": str(exc), "retry_delay_seconds": retry_delay},
                )
                registered = False
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30.0)


def main() -> None:
    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        logger.info("agent_shutdown")


if __name__ == "__main__":
    main()
