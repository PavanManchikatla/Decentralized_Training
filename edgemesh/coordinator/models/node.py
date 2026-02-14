from datetime import datetime, timezone

from pydantic import BaseModel, Field, model_validator

from models.enums import NodeStatus, RolePreference, TaskType


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NodeIdentity(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    ip: str = Field(min_length=1, max_length=64)
    port: int = Field(ge=0, le=65535)


class NodeCapabilities(BaseModel):
    task_types: list[TaskType] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    has_gpu: bool = False
    cpu_cores: int | None = Field(default=None, ge=1)
    cpu_threads: int | None = Field(default=None, ge=1)
    ram_total_gb: float | None = Field(default=None, ge=0)
    ram_gb: float | None = Field(default=None, ge=0)
    gpu_name: str | None = None
    vram_total_gb: float | None = Field(default=None, ge=0)
    os: str | None = None
    arch: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "NodeCapabilities":
        if self.ram_total_gb is None and self.ram_gb is not None:
            self.ram_total_gb = self.ram_gb
        if self.ram_gb is None and self.ram_total_gb is not None:
            self.ram_gb = self.ram_total_gb
        if self.gpu_name or self.vram_total_gb is not None:
            self.has_gpu = True
        return self


class NodeMetrics(BaseModel):
    cpu_percent: float = Field(default=0.0, ge=0, le=100)
    ram_used_gb: float = Field(default=0.0, ge=0)
    ram_percent: float = Field(default=0.0, ge=0, le=100)
    gpu_percent: float | None = Field(default=None, ge=0, le=100)
    vram_used_gb: float | None = Field(default=None, ge=0)
    running_jobs: int = Field(default=0, ge=0)
    heartbeat_ts: datetime = Field(default_factory=_utc_now)
    extra: dict[str, float] = Field(default_factory=dict)


class NodePolicy(BaseModel):
    enabled: bool = True
    cpu_cap_percent: int = Field(default=100, ge=0, le=100)
    gpu_cap_percent: int | None = Field(default=None, ge=0, le=100)
    ram_cap_percent: int = Field(default=100, ge=0, le=100)
    task_allowlist: list[TaskType] = Field(default_factory=lambda: list(TaskType))
    role_preference: RolePreference = RolePreference.AUTO


class Node(BaseModel):
    identity: NodeIdentity
    capabilities: NodeCapabilities = Field(default_factory=NodeCapabilities)
    metrics: NodeMetrics = Field(default_factory=NodeMetrics)
    policy: NodePolicy = Field(default_factory=NodePolicy)
    status: NodeStatus = NodeStatus.UNKNOWN
    last_seen: datetime = Field(default_factory=_utc_now)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class NodeDetail(BaseModel):
    node: Node
    metrics_history: list[NodeMetrics] | None = None


class NodeUpdateEvent(BaseModel):
    node_id: str
    status: NodeStatus
    metrics: NodeMetrics
    updated_at: datetime = Field(default_factory=_utc_now)
