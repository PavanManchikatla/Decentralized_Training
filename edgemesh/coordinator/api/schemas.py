from pydantic import BaseModel, Field, model_validator

from models import TaskType


class AgentCapabilitiesPayload(BaseModel):
    cpu_cores: int | None = Field(default=None, ge=1)
    cpu_threads: int | None = Field(default=None, ge=1)
    ram_total_gb: float | None = Field(default=None, ge=0)
    gpu_name: str | None = None
    vram_total_gb: float | None = Field(default=None, ge=0)
    os: str | None = None
    arch: str | None = None
    task_types: list[TaskType] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def default_task_types(self) -> "AgentCapabilitiesPayload":
        if not self.task_types:
            self.task_types = list(TaskType)
        return self


class AgentRegisterV1Request(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    ip: str = Field(min_length=1, max_length=64)
    port: int = Field(ge=0, le=65535)
    capabilities: AgentCapabilitiesPayload


class AgentHeartbeatMetricsPayload(BaseModel):
    cpu_percent: float = Field(ge=0, le=100)
    ram_used_gb: float = Field(ge=0)
    ram_percent: float = Field(ge=0, le=100)
    gpu_percent: float | None = Field(default=None, ge=0, le=100)
    vram_used_gb: float | None = Field(default=None, ge=0)
    running_jobs: int = Field(default=0, ge=0)


class AgentHeartbeatV1Request(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    metrics: AgentHeartbeatMetricsPayload


class SimulateScheduleRequest(BaseModel):
    task_type: str = Field(min_length=1, max_length=64)


class CandidateScore(BaseModel):
    node_id: str
    eligible: bool
    score: float
    reasons: list[str] = Field(default_factory=list)


class SimulateScheduleResponse(BaseModel):
    task_type: TaskType
    chosen_node_id: str | None = None
    reason: str | None = None
    ranked_candidates: list[CandidateScore] = Field(default_factory=list)


class ClusterSummaryResponse(BaseModel):
    total_nodes: int
    online_nodes: int
    offline_nodes: int
    total_effective_cpu_threads: float
    total_effective_ram_gb: float
    total_effective_vram_gb: float
    active_running_jobs_total: int
