"""Episode annotation endpoints; importing these requires no ROS runtime."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from annotations.models import AnnotationJob, AnnotationStatus
from annotations.service import (
    AnnotationConflictError,
    AnnotationService,
    AnnotationUnavailableError,
    get_annotation_service,
)
from annotations.store import JobStoreError

router = APIRouter(prefix="/api/v1/episodes/{episode_id}/annotations", tags=["Annotations"])


@router.get("", response_model=AnnotationStatus)
def status(episode_id: UUID, service: AnnotationService = Depends(get_annotation_service)) -> AnnotationStatus:
    """Read optional integration availability and the latest attempt."""
    try:
        return service.status(episode_id)
    except AnnotationConflictError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (AnnotationUnavailableError, JobStoreError) as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("", response_model=AnnotationJob, status_code=202)
def start(episode_id: UUID, service: AnnotationService = Depends(get_annotation_service)) -> AnnotationJob:
    """Submit a saved episode to Nomadic for action annotation."""
    try:
        return service.submit(episode_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except AnnotationConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except (AnnotationUnavailableError, JobStoreError) as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/download")
def download(episode_id: UUID, service: AnnotationService = Depends(get_annotation_service)) -> Response:
    """Download the normalized result, including float times and provenance."""
    try:
        current = service.status(episode_id).job
    except (AnnotationConflictError, AnnotationUnavailableError, JobStoreError) as exc:
        raise HTTPException(503, str(exc)) from exc
    if current is None or current.state != "completed":
        raise HTTPException(409, "Annotations are not complete.")
    return Response(
        current.model_dump_json(indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{episode_id}-annotations.json"'},
    )


@router.post("/refresh", response_model=AnnotationJob, status_code=202)
def refresh(episode_id: UUID, service: AnnotationService = Depends(get_annotation_service)) -> AnnotationJob:
    """Refresh a saved remote reference without submitting another recording."""
    try:
        return service.refresh(episode_id)
    except AnnotationConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (AnnotationUnavailableError, JobStoreError) as exc:
        raise HTTPException(503, str(exc)) from exc
