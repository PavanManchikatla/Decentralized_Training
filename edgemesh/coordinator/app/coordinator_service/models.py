from datetime import datetime

from pydantic import BaseModel, Field


class AgentRegisterRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class HeartbeatRequest(BaseModel):
    status: str = Field(default="healthy", min_length=1, max_length=64)
    metrics: dict[str, float] = Field(default_factory=dict)


class AgentView(BaseModel):
    agent_id: str
    capabilities: list[str]
    metadata: dict[str, str | int | float | bool | None]
    status: str
    metrics: dict[str, float]
    last_seen: datetime
    is_stale: bool


class HealthResponse(BaseModel):
    status: str
