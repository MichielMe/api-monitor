from typing import Any, Dict

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint

    Returns the status of the API Monitor service.
    """
    return {"status": "healthy", "service": "api-monitor"}
