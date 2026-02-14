from fastapi import APIRouter

from coordinator_service.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
@router.get("/api/health", response_model=HealthResponse, include_in_schema=False)
async def health() -> HealthResponse:
    """Health probe endpoint.

    Example response:
    {
      "status": "ok"
    }
    """

    return HealthResponse(status="ok")
