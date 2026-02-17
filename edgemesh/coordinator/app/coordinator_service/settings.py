import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    host: str
    port: int
    log_level: str
    heartbeat_ttl_seconds: int
    node_stale_seconds: int
    task_lease_seconds: int
    task_recovery_interval_seconds: int
    cors_origins: list[str]
    db_url: str
    edge_mesh_shared_secret: str

    @classmethod
    def from_env(cls) -> "Settings":
        cors_origins = [
            origin.strip()
            for origin in os.getenv(
                "COORDINATOR_CORS_ORIGINS", "http://localhost:5173"
            ).split(",")
            if origin.strip()
        ]

        return cls(
            host=os.getenv("COORDINATOR_HOST", "0.0.0.0"),
            port=int(os.getenv("COORDINATOR_PORT", "8000")),
            log_level=os.getenv("COORDINATOR_LOG_LEVEL", "INFO"),
            heartbeat_ttl_seconds=int(
                os.getenv("COORDINATOR_HEARTBEAT_TTL_SECONDS", "60")
            ),
            node_stale_seconds=int(os.getenv("NODE_STALE_SECONDS", "15")),
            task_lease_seconds=int(os.getenv("TASK_LEASE_SECONDS", "30")),
            task_recovery_interval_seconds=int(
                os.getenv("TASK_RECOVERY_INTERVAL_SECONDS", "3")
            ),
            cors_origins=cors_origins,
            db_url=os.getenv("COORDINATOR_DB_URL", "sqlite:///./coordinator.db"),
            edge_mesh_shared_secret=os.getenv("EDGE_MESH_SHARED_SECRET", "").strip(),
        )
