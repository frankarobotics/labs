from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response model for health checks."""

    status: str
