import os
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException

from api.auth import require_agent_secret
from api.schemas import (
    TaskPullRequest,
    TaskPullResponse,
    TaskResultSubmitRequest,
    TaskResultSubmitResponse,
)
from api.state import job_event_bus
from db import get_job, pull_task_for_node, submit_task_result
from models import Job, JobUpdateEvent, TaskResult

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _lease_seconds() -> int:
    return int(os.getenv("TASK_LEASE_SECONDS", "30"))


async def _publish_job_update(job: Job) -> None:
    await job_event_bus.publish(
        JobUpdateEvent(
            job_id=job.id,
            status=job.status,
            total_tasks=job.total_tasks,
            completed_tasks=job.completed_tasks,
            failed_tasks=job.failed_tasks,
            updated_at=job.updated_at,
        )
    )


@router.post(
    "/pull",
    response_model=TaskPullResponse,
    dependencies=[Depends(require_agent_secret)],
)
async def pull_task(
    payload: TaskPullRequest = Body(
        ...,
        examples={
            "default": {
                "summary": "Agent pulls next task",
                "value": {"node_id": "node-123"},
            }
        },
    ),
) -> TaskPullResponse:
    """Pull the next eligible task for a node using scheduler + policy constraints."""

    task = pull_task_for_node(node_id=payload.node_id, lease_seconds=_lease_seconds())
    if task is not None:
        job = get_job(task.job_id)
        if job is not None:
            await _publish_job_update(job)
    return TaskPullResponse(task=task)


@router.post(
    "/{task_id}/result",
    response_model=TaskResultSubmitResponse,
    dependencies=[Depends(require_agent_secret)],
)
async def submit_result(
    task_id: str,
    payload: TaskResultSubmitRequest = Body(
        ...,
        examples={
            "success": {
                "summary": "Task completed",
                "value": {
                    "node_id": "node-123",
                    "success": True,
                    "output": {"items_processed": 128},
                    "duration_ms": 380,
                },
            }
        },
    ),
) -> TaskResultSubmitResponse:
    """Submit task execution result and trigger job aggregation.

    Failed task results are automatically requeued until `max_retries` is reached.
    """

    try:
        task, job = submit_task_result(
            TaskResult(
                task_id=task_id,
                node_id=payload.node_id,
                success=payload.success,
                output=payload.output,
                duration_ms=payload.duration_ms,
                created_at=_utc_now(),
            )
        )
        await _publish_job_update(job)
        return TaskResultSubmitResponse(task=task, job=job)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"Task '{task_id}' not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
