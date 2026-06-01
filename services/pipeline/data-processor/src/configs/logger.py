"""Configure loguru for the application."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class LoggerConfig(BaseSettings):
    """Configuration for the logger."""

    log_level: str = Field(default="DEBUG", alias="LOG_LEVEL")
    path_prefix: str = Field(default="services/pipeline/data-processor/", alias="PATH_PREFIX")


@lru_cache
def load_logger_config() -> LoggerConfig:
    """Load configuration for the logger. Cached to avoid repeated validation.

    Returns:
        LoggerConfig: Configuration for the logger.
    """
    return LoggerConfig()
