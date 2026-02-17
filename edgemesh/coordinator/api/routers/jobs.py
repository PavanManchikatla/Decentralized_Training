import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, HTTPException, Query, status

from api.schemas import DemoJobBurstResponse, JobCreateRequest, JobStatusUpdateRequest
from api.state import job_event_bus
from db import (
    assign_job,
    create_job,
    create_tasks,
    get_job,
    get_nodes,
    list_jobs,
    list_tasks,
    transition_job_status,
)
from models import Job, JobStatus, JobUpdateEvent, Task, TaskType
from scheduler import evaluate_node_eligibility, score_node

router = APIRouter(prefix="/v1", tags=["jobs"])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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


def _parse_task_type(raw: str) -> TaskType:
    normalized = raw.strip().upper()
    mapping = {
        "INFER": TaskType.INFERENCE,
        "INFERENCE": TaskType.INFERENCE,
        "EMBED": TaskType.EMBEDDINGS,
        "EMBEDDING": TaskType.EMBEDDINGS,
        "EMBEDDINGS": TaskType.EMBEDDINGS,
        "INDEX": TaskType.INDEX,
        "TOKENIZE": TaskType.TOKENIZE,
        "PREPROCESS": TaskType.PREPROCESS,
        "PREPROCESSING": TaskType.PREPROCESS,
    }

    task_type = mapping.get(normalized)
    if task_type is None:
        raise HTTPException(status_code=422, detail=f"Unsupported task_type '{raw}'")
    return task_type


def _parse_job_status(raw: str) -> JobStatus:
    normalized = raw.strip().upper()
    mapping = {
        "QUEUED": JobStatus.QUEUED,
        "RUNNING": JobStatus.RUNNING,
        "COMPLETED": JobStatus.COMPLETED,
        "FAILED": JobStatus.FAILED,
        "CANCELLED": JobStatus.CANCELLED,
    }

    parsed = mapping.get(normalized)
    if parsed is None:
        raise HTTPException(status_code=422, detail=f"Unsupported status '{raw}'")
    return parsed


def _pick_node_for_task(task_type: TaskType) -> str | None:
    candidates: list[tuple[str, bool, float]] = []

    for node in get_nodes():
        eligible, _ = evaluate_node_eligibility(node, task_type)
        score = score_node(node, task_type)
        candidates.append((node.identity.node_id, eligible, score))

    candidates.sort(key=lambda item: (item[1], item[2]), reverse=True)
    chosen = next((candidate for candidate in candidates if candidate[1]), None)
    return chosen[0] if chosen is not None else None


def _build_task_payloads(
    payload: JobCreateRequest, task_type: TaskType
) -> list[dict[str, object]]:
    if payload.payload_items:
        return [
            {
                "task_index": index,
                "task_type": task_type.value,
                "item": item,
                "payload_ref": payload.payload_ref,
            }
            for index, item in enumerate(payload.payload_items)
        ]

    return [
        {
            "task_index": index,
            "task_type": task_type.value,
            "payload_ref": payload.payload_ref,
        }
        for index in range(payload.task_count)
    ]


@router.post("/jobs", response_model=Job, status_code=status.HTTP_201_CREATED)
async def create_job_route(
    payload: JobCreateRequest = Body(
        ...,
        examples={
            "embed": {
                "summary": "Create embedding job",
                "value": {
                    "task_type": "EMBED",
                    "payload_ref": "s3://bucket/chunk-001.json",
                    "task_count": 8,
                    "max_task_retries": 2,
                },
            }
        },
    ),
) -> Job:
    """Create a distributed job and split it into executable tasks."""

    task_type = _parse_task_type(payload.task_type)

    job = create_job(
        Job(
            id=f"job-{uuid.uuid4().hex[:12]}",
            type=task_type,
            status=JobStatus.QUEUED,
            payload_ref=payload.payload_ref,
            updated_at=_utc_now(),
        )
    )

    task_payloads = _build_task_payloads(payload, task_type)
    create_tasks(
        job_id=job.id,
        task_type=task_type,
        payloads=task_payloads,
        max_retries=payload.max_task_retries,
    )

    refreshed = get_job(job.id)
    if refreshed is None:
        raise HTTPException(status_code=500, detail="Failed to load created job")

    await _publish_job_update(refreshed)
    return refreshed


@router.get("/jobs", response_model=list[Job])
async def list_jobs_route(
    status_filter: str | None = Query(default=None, alias="status"),
    task_type_filter: str | None = Query(default=None, alias="task_type"),
    node_id: str | None = Query(default=None),
) -> list[Job]:
    """List jobs with optional filters by status, task_type, and node_id."""

    status_value = (
        _parse_job_status(status_filter) if status_filter is not None else None
    )
    task_type_value = (
        _parse_task_type(task_type_filter) if task_type_filter is not None else None
    )
    return list_jobs(status=status_value, task_type=task_type_value, node_id=node_id)


@router.get("/jobs/{job_id}", response_model=Job)
async def get_job_route(job_id: str) -> Job:
    """Get a single job by id."""

    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job


@router.get("/jobs/{job_id}/tasks", response_model=list[Task])
async def list_job_tasks_route(job_id: str) -> list[Task]:
    """List all tasks for a job including assignment/retry state."""

    if get_job(job_id) is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return list_tasks(job_id=job_id)


@router.post("/jobs/{job_id}/status", response_model=Job)
async def transition_job_status_route(
    job_id: str,
    payload: JobStatusUpdateRequest = Body(
        ...,
        examples={
            "running": {"summary": "Start job", "value": {"status": "RUNNING"}},
            "failed": {
                "summary": "Fail job",
                "value": {"status": "FAILED", "error": "GPU memory exhausted"},
            },
        },
    ),
) -> Job:
    """Manual override for job status transition path QUEUED -> RUNNING -> COMPLETED/FAILED."""

    try:
        updated = transition_job_status(
            job_id=job_id, new_status=payload.status, error=payload.error
        )
        await _publish_job_update(updated)
        return updated
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"Job '{job_id}' not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/demo/jobs/create-embed-burst", response_model=DemoJobBurstResponse)
async def create_embed_burst(
    count: int = Query(default=20, ge=1, le=200),
    tasks_per_job: int = Query(default=6, ge=1, le=64),
) -> DemoJobBurstResponse:
    """Create a burst of EMBED jobs split into tasks for distributed execution demo."""

    jobs: list[Job] = []
    assigned_count = 0

    for index in range(count):
        job = create_job(
            Job(
                id=f"job-{uuid.uuid4().hex[:12]}",
                type=TaskType.EMBEDDINGS,
                status=JobStatus.QUEUED,
                payload_ref=f"demo://embed/{index:04d}",
                updated_at=_utc_now(),
            )
        )

        payloads = [
            {
                "task_index": task_index,
                "task_type": TaskType.EMBEDDINGS.value,
                "payload_ref": job.payload_ref,
                "text": f"demo chunk {index:04d}-{task_index:02d}",
            }
            for task_index in range(tasks_per_job)
        ]
        create_tasks(
            job_id=job.id,
            task_type=TaskType.EMBEDDINGS,
            payloads=payloads,
            max_retries=2,
        )

        assigned_node_id = _pick_node_for_task(TaskType.EMBEDDINGS)
        if assigned_node_id is not None:
            assigned_count += 1
            assign_job(job.id, assigned_node_id)

        refreshed = get_job(job.id)
        if refreshed is not None:
            jobs.append(refreshed)
            await _publish_job_update(refreshed)

    queued_count = sum(1 for item in jobs if item.status == JobStatus.QUEUED)
    running_count = sum(1 for item in jobs if item.status == JobStatus.RUNNING)
    completed_count = sum(1 for item in jobs if item.status == JobStatus.COMPLETED)
    failed_count = sum(1 for item in jobs if item.status == JobStatus.FAILED)

    return DemoJobBurstResponse(
        created_count=count,
        assigned_count=assigned_count,
        queued_count=queued_count,
        running_count=running_count,
        completed_count=completed_count,
        failed_count=failed_count,
        jobs=jobs,
    )
