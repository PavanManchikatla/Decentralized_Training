from datetime import datetime, timezone

from pydantic import BaseModel, Field

from models.enums import JobStatus, TaskType


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Job(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    type: TaskType
    status: JobStatus = JobStatus.QUEUED
    assigned_node_id: str | None = Field(default=None, max_length=128)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    error: str | None = None
