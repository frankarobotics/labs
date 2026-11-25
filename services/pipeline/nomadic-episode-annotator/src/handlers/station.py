"""Station-level endpoints that are not tied to one episode."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, SecretStr

from dependencies import get_annotation_service
from jobs.models import StationAccount
from jobs.service import AnnotationConflictError, AnnotationService, AnnotationUnavailableError

router = APIRouter(prefix="/api/v1/station", tags=["Station"])


class ConnectRequest(BaseModel):
    """An API key pasted by an operator; SecretStr keeps it out of logs and error echoes."""

    api_key: SecretStr


@router.post("/api-key", response_model=StationAccount)
def connect(request: ConnectRequest, service: AnnotationService = Depends(get_annotation_service)) -> StationAccount:
    """Check a Nomadic API key and connect this station to its account."""
    try:
        return service.connect(request.api_key.get_secret_value())
    except AnnotationConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except AnnotationUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc
