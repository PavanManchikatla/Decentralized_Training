from datetime import datetime, timezone

from pydantic import BaseModel, Field

from models.enums import JobStatus, TaskType


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Job(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    type: TaskType
    status: JobStatus = JobStatus.QUEUED
    payload_ref: str | None = Field(default=None, max_length=512)
    assigned_node_id: str | None = Field(default=None, max_length=128)
    attempts: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = Field(default=None, max_length=2048)

    total_tasks: int = Field(default=0, ge=0)
    queued_tasks: int = Field(default=0, ge=0)
    running_tasks: int = Field(default=0, ge=0)
    completed_tasks: int = Field(default=0, ge=0)
    failed_tasks: int = Field(default=0, ge=0)
    total_retries: int = Field(default=0, ge=0)
    assigned_nodes: list[str] = Field(default_factory=list)
    avg_task_duration_ms: float | None = Field(default=None, ge=0)
    throughput_tasks_per_minute: float | None = Field(default=None, ge=0)


class JobUpdateEvent(BaseModel):
    job_id: str
    status: JobStatus
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    updated_at: datetime = Field(default_factory=_utc_now)
