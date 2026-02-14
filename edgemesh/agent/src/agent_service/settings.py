import os
import socket
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    coordinator_url: str
    display_name: str
    agent_port: int
    heartbeat_seconds: float
    log_level: str
    state_file: Path

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            coordinator_url=os.getenv("COORDINATOR_URL", "http://localhost:8000").rstrip("/"),
            display_name=os.getenv("DISPLAY_NAME", socket.gethostname()),
            agent_port=int(os.getenv("AGENT_PORT", "9100")),
            heartbeat_seconds=float(os.getenv("HEARTBEAT_SECONDS", "2")),
            log_level=os.getenv("AGENT_LOG_LEVEL", "INFO"),
            state_file=Path(os.getenv("NODE_ID_FILE", "state/node_id.txt")),
        )
