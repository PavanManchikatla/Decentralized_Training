from fastapi import APIRouter, Body, HTTPException

from api.schemas import CandidateScore, SimulateScheduleRequest, SimulateScheduleResponse
from db import get_nodes
from models import TaskType
from scheduler import evaluate_node_eligibility, score_node

router = APIRouter(prefix="/v1/simulate", tags=["scheduler"])


def _parse_task_type(raw: str) -> TaskType:
    normalized = raw.strip().upper()
    mapping = {
        "INFER": TaskType.INFERENCE,
        "INFERENCE": TaskType.INFERENCE,
        "EMBED": TaskType.EMBEDDINGS,
        "EMBEDDING": TaskType.EMBEDDINGS,
        "EMBEDDINGS": TaskType.EMBEDDINGS,
        "PREPROCESS": TaskType.PREPROCESS,
        "PREPROCESSING": TaskType.PREPROCESS,
    }

    task_type = mapping.get(normalized)
    if task_type is None:
        raise HTTPException(status_code=422, detail=f"Unsupported task_type '{raw}'")
    return task_type


@router.post("/schedule", response_model=SimulateScheduleResponse)
async def simulate_schedule(
    payload: SimulateScheduleRequest = Body(
        ...,
        examples={
            "embed": {
                "summary": "Embedding task simulation",
                "value": {"task_type": "EMBED"},
            },
            "infer": {
                "summary": "Inference task simulation",
                "value": {"task_type": "INFER"},
            },
        },
    )
) -> SimulateScheduleResponse:
    """Simulate task scheduling and return ranked candidates.

    Response includes:
    - `chosen_node_id` when at least one node is eligible.
    - `reason` when no node is eligible.
    - `ranked_candidates` with scores and ineligibility reasons.
    """

    task_type = _parse_task_type(payload.task_type)
    nodes = get_nodes()

    candidates: list[CandidateScore] = []
    for node in nodes:
        eligible, reasons = evaluate_node_eligibility(node, task_type)
        score = score_node(node, task_type)
        candidates.append(
            CandidateScore(
                node_id=node.identity.node_id,
                eligible=eligible,
                score=score,
                reasons=reasons,
            )
        )

    candidates.sort(key=lambda item: (item.eligible, item.score), reverse=True)

    chosen = next((candidate for candidate in candidates if candidate.eligible), None)
    if chosen is None:
        return SimulateScheduleResponse(
            task_type=task_type,
            chosen_node_id=None,
            reason="No eligible nodes found",
            ranked_candidates=candidates,
        )

    return SimulateScheduleResponse(
        task_type=task_type,
        chosen_node_id=chosen.node_id,
        reason=None,
        ranked_candidates=candidates,
    )
