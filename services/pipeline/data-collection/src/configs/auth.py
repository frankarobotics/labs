"""Authentication configuration for JWT tokens."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field


class AuthConfig(BaseModel):
    """Configuration for authentication."""

    jwt_secret: str = Field(
        default_factory=lambda: os.getenv("JWT_SECRET", "dev-secret-change-in-production"),
        description="Secret key for signing JWT tokens",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="Algorithm for JWT token signing",
    )
    jwt_expiration_minutes: int = Field(
        default=1440,  # 24 hours
        description="JWT token expiration time in minutes",
    )


@lru_cache
def load_auth_config() -> AuthConfig:
    """Load authentication configuration from environment variables."""
    return AuthConfig()
