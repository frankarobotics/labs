"""Models for teleoperation endpoints."""

from pydantic import BaseModel


class TeleopResponse(BaseModel):
    """Response model for teleoperation endpoints."""

    status: str
    message: str


class TeleopStatusResponse(BaseModel):
    """Response model for teleoperation status endpoint."""

    status: str
    is_active: bool
