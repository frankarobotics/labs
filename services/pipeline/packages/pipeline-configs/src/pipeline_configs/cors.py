"""CORS configuration model, shared across the pipeline services."""

import os
from dataclasses import dataclass


@dataclass
class CORSConfig:
    """Configuration for Cross-Origin Resource Sharing (CORS) settings."""

    allow_origins: list[str]
    allow_credentials: bool
    allow_methods: list[str]
    allow_headers: list[str]
    expose_headers: list[str]
    max_age: int


def load_cors_config() -> CORSConfig:
    """Load CORS configuration from environment variables or default settings.

    Returns:
        CORSConfig: A configuration object with CORS settings
    """
    # Get CORS_ORIGINS from environment or use default "*"
    origins_str: str = os.environ.get("CORS_ORIGINS", "*")
    # Split by comma if multiple origins are specified
    origins: list[str] = [origin.strip() for origin in origins_str.split(",")]

    return CORSConfig(
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["*"],
        expose_headers=[
            "Content-Type",
            "Content-Length",
            "Content-Disposition",
            "X-Pagination",
            "X-Total-Count",
            "Location",
        ],
        max_age=600,  # Cache preflight requests for 10 minutes
    )
