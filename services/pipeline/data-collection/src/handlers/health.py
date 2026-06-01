"""Health check endpoints for the data collection service.

https://kubernetes.io/docs/reference/using-api/health-checks/#api-endpoints-for-health.
"""

from fastapi import APIRouter
from loguru import logger

from models.health import HealthResponse

router: APIRouter = APIRouter()


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """Health check endpoint.

    Returns:
        HealthResponse: Indicates if the service is healthy.
    """
    try:
        return HealthResponse(status="healthy")
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise


@router.get("/livez", response_model=HealthResponse)
def livez() -> HealthResponse:
    """Liveness check endpoint.

    Returns:
        HealthResponse: Indicates if the service is alive.
    """
    logger.info("[GET] /livez | Liveness check requested")
    try:
        response = HealthResponse(status="alive")
        logger.info("Service is alive")
        return response
    except Exception as e:
        logger.error(f"Liveness check failed: {e}")
        raise


@router.get("/readyz", response_model=HealthResponse)
def readyz() -> HealthResponse:
    """Readiness check endpoint.

    Returns:
        HealthResponse: Indicates if the service is ready to serve traffic.
    """
    logger.info("[GET] /readyz | Readiness check requested")
    try:
        response = HealthResponse(status="ready")
        logger.info("Service is ready")
        return response
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise
