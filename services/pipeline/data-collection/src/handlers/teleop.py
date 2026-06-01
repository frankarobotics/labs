"""Teleoperation endpoints handler.

This module provides endpoints to control teleoperation of the robot.
"""

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from dependencies import get_teleop_service
from models.teleop import TeleopResponse, TeleopStatusResponse
from services.teleop import TeleopService

router: APIRouter = APIRouter()


@router.post("/api/v1/teleop/start", response_model=TeleopResponse)
def start_teleop(
    teleop_service: TeleopService = Depends(get_teleop_service),
) -> TeleopResponse:
    """Start teleoperation mode.

    Transitions the system from IDLE to TELEOP state, allowing the operator to control the robot.

    Args:
        teleop_service: Injected TeleopService dependency.

    Returns:
        TeleopResponse: Result of the start teleoperation operation.

    Raises:
        HTTPException: If the operation fails.
    """
    logger.info("[POST] /api/v1/teleop/start | Start teleop requested")
    try:
        return teleop_service.start_teleop()
    except Exception as e:
        logger.error(f"Failed to start teleoperation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start teleoperation: {e}") from e


@router.post("/api/v1/teleop/stop", response_model=TeleopResponse)
def stop_teleop(
    teleop_service: TeleopService = Depends(get_teleop_service),
) -> TeleopResponse:
    """Stop teleoperation mode.

    Stops teleoperation and transitions the system back to IDLE state.
    Note: This is a custom transition not explicitly defined in the state machine.

    Args:
        teleop_service: Injected TeleopService dependency.

    Returns:
        TeleopResponse: Result of the stop teleoperation operation.

    Raises:
        HTTPException: If the operation fails.
    """
    logger.info("[POST] /api/v1/teleop/stop | Stop teleop requested")
    try:
        return teleop_service.stop_teleop()
    except Exception as e:
        logger.error(f"Failed to stop teleoperation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop teleoperation: {e}") from e


@router.post("/api/v1/teleop/start_syncing", response_model=TeleopResponse)
def start_syncing(
    teleop_service: TeleopService = Depends(get_teleop_service),
) -> TeleopResponse:
    """Start syncing.

    Transitions the system from READY to SYNCING state.

    Args:
        teleop_service: Injected TeleopService dependency.

    Returns:
        TeleopResponse: Result of the start syncing operation.

    Raises:
        HTTPException: If the operation fails.
    """
    logger.info("[POST] /api/v1/teleop/start_syncing | Start syncing requested")
    try:
        return teleop_service.start_syncing()
    except Exception as e:
        logger.error(f"Failed to start syncing: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start syncing: {e}") from e


@router.get("/api/v1/teleop/status", response_model=TeleopStatusResponse)
def teleop_status(
    teleop_service: TeleopService = Depends(get_teleop_service),
) -> TeleopStatusResponse:
    """Get the current status of teleoperation.

    Args:
        teleop_service: Injected TeleopService dependency.

    Returns:
        TeleopStatusResponse: Indicates if teleoperation is active or not.
    """
    logger.info("[GET] /api/v1/teleop/status | Teleop status requested")
    try:
        return teleop_service.get_teleop_status()
    except Exception as e:
        logger.error(f"Failed to get teleoperation status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get teleoperation status: {e}") from e
