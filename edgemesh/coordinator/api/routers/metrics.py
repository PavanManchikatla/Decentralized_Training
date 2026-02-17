from fastapi import APIRouter

from api.schemas import ExecutionMetricsResponse
from db import get_execution_metrics

router = APIRouter(prefix="/v1/metrics", tags=["metrics"])


@router.get("/execution", response_model=ExecutionMetricsResponse)
async def execution_metrics() -> ExecutionMetricsResponse:
    """Return execution throughput, duration, and reliability metrics for distributed tasks."""

    payload = get_execution_metrics()
    return ExecutionMetricsResponse.model_validate(payload)
