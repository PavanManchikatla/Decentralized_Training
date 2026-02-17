from pydantic import BaseModel, Field, model_validator

from models import Job, JobStatus, Task, TaskType


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


class JobCreateRequest(BaseModel):
    task_type: str = Field(min_length=1, max_length=64)
    payload_ref: str | None = Field(default=None, max_length=512)
    task_count: int = Field(default=1, ge=1, le=500)
    payload_items: list[str] | None = None
    max_task_retries: int = Field(default=2, ge=0, le=20)


class JobStatusUpdateRequest(BaseModel):
    status: JobStatus
    error: str | None = Field(default=None, max_length=2048)


class DemoJobBurstResponse(BaseModel):
    created_count: int
    assigned_count: int
    queued_count: int
    running_count: int
    completed_count: int
    failed_count: int
    jobs: list[Job] = Field(default_factory=list)


class TaskPullRequest(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)


class TaskPullResponse(BaseModel):
    task: Task | None = None


class TaskResultSubmitRequest(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    success: bool
    output: dict[str, object] | None = None
    duration_ms: int = Field(ge=0)


class TaskResultSubmitResponse(BaseModel):
    task: Task
    job: Job


class ExecutionMetricsResponse(BaseModel):
    total_results: int
    success_results: int
    failed_results: int
    avg_duration_ms: float | None = None
    throughput_tasks_per_minute: float
    node_reliability: dict[str, float] = Field(default_factory=dict)
