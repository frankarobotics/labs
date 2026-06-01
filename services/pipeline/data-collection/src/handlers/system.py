"""System endpoints handler."""

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from dependencies import get_system_service
from models.system import SystemGetResponse
from services.system import SystemService

router: APIRouter = APIRouter()


@router.get("/api/v1/system/info", response_model=SystemGetResponse)
def get_system_info(
    system_service: SystemService = Depends(get_system_service),
) -> SystemGetResponse:
    """Retrieve all available system information.

    Args:
        system_service: Injected SystemService dependency.

    Returns:
        SystemGetResponse: System information response object.

    Raises:
        HTTPException: If an error occurs while retrieving system information.
    """
    # logger.info("[GET] /api/v1/system/info | System info requested")
    try:
        system: SystemGetResponse = system_service.get_system_info()
        # logger.info("Retrieved system information")
        return SystemGetResponse.model_validate(system)
    except Exception as e:
        logger.error(f"Failed to get system information: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get system information: {e}") from e
