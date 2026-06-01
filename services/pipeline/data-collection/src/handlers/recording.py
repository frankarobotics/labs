"""Recording endpoints handler.

This module provides endpoints to control recording operations.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from dependencies import get_recording_service
from models.episode import EpisodeLabel
from models.recording import (
    DiscardRecordingResponse,
    SaveRecordingResponse,
    StartRecordingResponse,
    StopRecordingResponse,
)
from services.recording import RecordingService

router: APIRouter = APIRouter()


@router.post("/api/v1/recording/start", response_model=StartRecordingResponse)
def start_recording(
    task_id: UUID = Query(
        ..., example="b06d85e1-c053-49db-acbb-685fc64ddf8a", description="Unique identifier for the task."
    ),
    recording_service: RecordingService = Depends(get_recording_service),
) -> StartRecordingResponse:
    """Start a new recording for a given episode and task.

    Args:
        task_id: Unique identifier for the task.
        recording_service: Injected RecordingService dependency.

    Returns:
        StartRecordingResponse: Result of the start recording operation.

    Raises:
        HTTPException: If the operation fails.
    """
    logger.info(f"[POST] /api/v1/recording/start | {task_id=}")
    try:
        return recording_service.start_recording(task_id)
    except Exception as e:
        logger.error(f"Failed to start recording: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start recording: {e}") from e


@router.post("/api/v1/recording/stop", response_model=StopRecordingResponse)
def stop_recording(
    recording_service: RecordingService = Depends(get_recording_service),
) -> StopRecordingResponse:
    """Stop the current recording.

    Args:
        recording_service: Injected RecordingService dependency.

    Returns:
        StopRecordingResponse: Result of the stop recording operation.

    Raises:
        HTTPException: If the operation fails.
    """
    logger.info("[POST] /api/v1/recording/stop")
    try:
        return recording_service.stop_recording()
    except Exception as e:
        logger.error(f"Failed to stop recording: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop recording: {e}") from e


@router.post("/api/v1/recording/save", response_model=SaveRecordingResponse)
def save_recording(
    label: EpisodeLabel = Query(..., description="Label for the episode"),
    tags: list[str] | None = Query(None, description="Tags for the save operation"),
    recording_service: RecordingService = Depends(get_recording_service),
) -> SaveRecordingResponse:
    """Save the current recording, with tags indicating success or failure.

    Args:
        tags: Optional tags for the save operation (must be 'successful' or 'failed').
        label: Label for the episode (REVIEW_SUCCESS or REVIEW_FAILED).
        recording_service: Injected RecordingService dependency.

    Returns:
        SaveRecordingResponse: Result of the save operation.

    Raises:
        HTTPException: If the operation fails.
    """
    logger.info(f"[POST] /api/v1/recording/save | {label=}, {tags=}")
    try:
        response: SaveRecordingResponse = recording_service.save_episode(tags=tags or [], label=label)
        return response
    except Exception as e:
        logger.error(f"Failed to save episode: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save episode: {e}") from e


@router.post("/api/v1/recording/discard", response_model=DiscardRecordingResponse)
def discard_recording(
    recording_service: RecordingService = Depends(get_recording_service),
) -> DiscardRecordingResponse:
    """Discard the current recording.

    Args:
        recording_service: Injected RecordingService dependency.

    Returns:
        DiscardRecordingResponse: Result of the discard operation.

    Raises:
        HTTPException: If the operation fails.
    """
    logger.info("[POST] /api/v1/recording/discard")
    try:
        return recording_service.discard_episode()
    except Exception as e:
        logger.error(f"Failed to discard episode: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to discard episode: {e}") from e
