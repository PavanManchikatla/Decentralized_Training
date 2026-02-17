from datetime import datetime, timezone

from pydantic import BaseModel, Field

from models.enums import TaskStatus, TaskType


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Task(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    job_id: str = Field(min_length=1, max_length=128)
    type: TaskType
    payload: dict[str, object] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.QUEUED
    assigned_node_id: str | None = Field(default=None, max_length=128)
    retries: int = Field(default=0, ge=0)
    max_retries: int = Field(default=2, ge=0, le=20)
    lease_expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = Field(default=None, max_length=2048)


class TaskResult(BaseModel):
    task_id: str = Field(min_length=1, max_length=128)
    node_id: str = Field(min_length=1, max_length=128)
    success: bool
    output: dict[str, object] | None = None
    duration_ms: int = Field(ge=0)
    created_at: datetime = Field(default_factory=_utc_now)
