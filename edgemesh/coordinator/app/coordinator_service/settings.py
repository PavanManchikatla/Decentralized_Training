import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    host: str
    port: int
    log_level: str
    heartbeat_ttl_seconds: int
    node_stale_seconds: int
    cors_origins: list[str]
    db_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        cors_origins = [
            origin.strip()
            for origin in os.getenv("COORDINATOR_CORS_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        ]

        return cls(
            host=os.getenv("COORDINATOR_HOST", "0.0.0.0"),
            port=int(os.getenv("COORDINATOR_PORT", "8000")),
            log_level=os.getenv("COORDINATOR_LOG_LEVEL", "INFO"),
            heartbeat_ttl_seconds=int(os.getenv("COORDINATOR_HEARTBEAT_TTL_SECONDS", "60")),
            node_stale_seconds=int(os.getenv("NODE_STALE_SECONDS", "15")),
            cors_origins=cors_origins,
            db_url=os.getenv("COORDINATOR_DB_URL", "sqlite:///./coordinator.db"),
        )
