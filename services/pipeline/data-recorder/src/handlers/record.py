"""Record endpoints handler.

This module provides endpoints to control data recording operations.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from configs.data_recorder import DataRecorderConfig, load_data_recorder_config
from models.record import (
    DeleteRecordResponse,
    RecordStateResponse,
    RecordStatusResponse,
    StartRecordRequest,
    StartRecordResponse,
    StopRecordResponse,
)
from repos.record_metadata import RecordMetadataRepo
from services.record import RecordService

router: APIRouter = APIRouter()


def get_record_service() -> RecordService:
    """Dependency for getting the record service singleton.

    Returns:
        The record service singleton instance.
    """
    config: DataRecorderConfig = load_data_recorder_config()
    return RecordService(config=config, record_metadata_repo=RecordMetadataRepo(config.output_path))


@router.post("/api/v1/record/start", response_model=StartRecordResponse)
def start_recording(
    request: StartRecordRequest, record_service: RecordService = Depends(get_record_service)
) -> StartRecordResponse:
    """Start recording data.

    Args:
        request: The recording request containing the episode ID.
        record_service: The record service instance.

    Returns:
        A response indicating the result of the operation.
    """
    logger.info(f"Start recording requested with episode ID: {request.episode_id}")

    try:
        return record_service.start_recording(request.episode_id)
    except Exception as e:
        logger.error(f"Failed to start recording: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start recording: {e}") from e


@router.post("/api/v1/record/stop", response_model=StopRecordResponse)
def stop_recording(
    record_service: RecordService = Depends(get_record_service),
) -> StopRecordResponse:
    """Stop recording data.

    Args:
        record_service: The record service instance.

    Returns:
        A response indicating the result of the operation.
    """
    logger.info("Stop recording requested")

    try:
        return record_service.stop_recording()
    except Exception as e:
        logger.error(f"Failed to stop recording: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop recording: {e}") from e


@router.get("/api/v1/record/status/{episode_id}", response_model=RecordStatusResponse)
def record_status(
    episode_id: UUID,
    record_service: RecordService = Depends(get_record_service),
) -> RecordStatusResponse:
    """Get the current status of data recording.

    Args:
        episode_id: The UUID of the episode to check the status for.
        record_service: The record service instance.

    Returns:
        A response indicating if recording is active or not, the current episode ID if available,
        and metadata information about the recording if available.
    """
    logger.info(f"Record status requested for episode ID: {episode_id}")

    return record_service.get_recording_status(episode_id)


@router.delete("/api/v1/record/{episode_id}", response_model=DeleteRecordResponse)
def delete_recording(
    episode_id: UUID,
    record_service: RecordService = Depends(get_record_service),
) -> DeleteRecordResponse:
    """Delete a recorded episode.

    Args:
        episode_id: The UUID of the episode to delete.
        record_service: The record service instance.

    Returns:
        A response indicating the result of the operation.
    """
    logger.info(f"Delete recording requested for episode ID: {episode_id}")

    try:
        return record_service.delete_recording(episode_id)
    except Exception as e:
        logger.error(f"Failed to delete recording: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete recording: {e}") from e


@router.get("/api/v1/record/state", response_model=RecordStateResponse)
def record_state(
    record_service: RecordService = Depends(get_record_service),
) -> RecordStateResponse:
    """Get the current status of data recording.

    Args:
        episode_id: The UUID of the episode to check the status for.
        record_service: The record service instance.

    Returns:
        A response indicating if recording is active or not, the current episode ID if available,
        and metadata information about the recording if available.
    """
    logger.info("Record state requested")

    return record_service.get_record_state()
