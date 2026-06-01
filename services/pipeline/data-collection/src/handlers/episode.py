"""Episode endpoints handler.

This module provides endpoints to control episode operations.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from dependencies import get_episode_service
from models.episode import (
    EpisodeDeleteResponse,
    EpisodePatchRequest,
    EpisodeProcessed,
    EpisodeResponse,
    EpisodeShipped,
)
from services.episode import EpisodeService

router: APIRouter = APIRouter()


@router.get("/api/v1/episodes", response_model=list[EpisodeResponse])
def get_episodes(  # noqa: PLR0913
    episode_service: EpisodeService = Depends(get_episode_service),
    task_id: UUID | None = Query(
        None, example="b06d85e1-c053-49db-acbb-685fc64ddf8a", description="Optional task identifier to filter episodes."
    ),
    status: str | None = Query(None),
    processed: EpisodeProcessed | None = Query(
        None, description="Optional processed filter: DEFAULT, SUCCESS, or ERROR"
    ),
    shipped: EpisodeShipped | None = Query(None, description="Optional shipped filter: DEFAULT, SUCCESS, or ERROR"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[EpisodeResponse]:
    """Retrieve a list of episodes, optionally filtered by status or task.

    Args:
        episode_service: Injected EpisodeService dependency.
        task_id: Optional task identifier to filter episodes.
        status: Optional status to filter episodes.
        processed: Optional processed status to filter episodes.
        shipped: Optional shipped status to filter episodes.
        limit: Maximum number of episodes to return (default 100).
        offset: Number of episodes to skip (default 0).

    Returns:
        List of EpisodeResponse objects matching the filters.

    Raises:
        HTTPException: If an error occurs during retrieval.
    """
    logger.debug(f"[GET] /api/v1/episodes | Filters: {status=}, {shipped=}, {task_id=}, {limit=}, {offset=}")
    try:
        return episode_service.get_episodes(
            status=status,
            processed=processed.value if processed else None,
            shipped=shipped.value if shipped else None,
            task_id=task_id,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error(f"Failed to get episodes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get episodes: {e}") from e


@router.get("/api/v1/episodes/{episode_id}", response_model=EpisodeResponse)
def get_episode_by_id(
    episode_id: UUID,
    episode_service: EpisodeService = Depends(get_episode_service),
) -> EpisodeResponse:
    """Retrieve a single episode by its unique identifier.

    Args:
        episode_id: Unique identifier for the episode.
        episode_service: Injected EpisodeService dependency.

    Returns:
        EpisodeResponse: The episode data if found.

    Raises:
        HTTPException: If the episode is not found or retrieval fails.
    """
    logger.info(f"[GET] /api/v1/episodes/{episode_id} | {episode_id=}")
    try:
        episode: EpisodeResponse | None = episode_service.get_episode_by_id(episode_id)
        if episode is None:
            logger.warning(f"Episode not found: {episode_id=}")
            raise HTTPException(status_code=404, detail="Episode not found")
        return episode
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get episode: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get episode: {e}") from e


@router.delete("/api/v1/episodes/{episode_id}", response_model=EpisodeDeleteResponse)
def delete_episode(
    episode_id: UUID,
    episode_service: EpisodeService = Depends(get_episode_service),
) -> EpisodeDeleteResponse:
    """Delete an episode and its recording by id."""
    logger.info(f"[DELETE] /api/v1/episodes/{episode_id} | {episode_id=}")
    try:
        return episode_service.delete_episode(episode_id)
    except Exception as e:
        logger.error(f"Failed to delete episode: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete episode: {e}") from e


@router.patch("/api/v1/episodes/{episode_id}", response_model=EpisodeResponse)
def patch_episode(
    episode_id: UUID,
    patch: EpisodePatchRequest,
    episode_service: EpisodeService = Depends(get_episode_service),
) -> EpisodeResponse:
    """Patch mutable fields of an episode (shipped, message)."""
    logger.info(f"[PATCH] /api/v1/episodes/{episode_id} | {patch=}")
    try:
        return episode_service.patch_episode(
            episode_id,
            processed=patch.processed.value if patch.processed else None,
            shipped=patch.shipped.value if patch.shipped else None,
            message=patch.message,
            object_url=patch.object_url,
        )
    except Exception as e:
        logger.error(f"Failed to patch episode: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to patch episode: {e}") from e
