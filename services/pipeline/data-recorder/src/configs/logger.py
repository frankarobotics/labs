"""Configure loguru for the application."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class LoggerConfig(BaseSettings):
    """Configuration for the logger."""

    log_level: str = Field(default="DEBUG", alias="LOG_LEVEL")
    file_path: str | None = Field(default=None, alias="LOG_FILE_PATH")
    rotation: str = Field(default="10 MB", alias="LOG_ROTATION")
    retention: str = Field(default="1 week", alias="LOG_RETENTION")
    compression: str = Field(default="zip", alias="LOG_COMPRESSION")
    serialize: bool = Field(default=False, alias="LOG_SERIALIZE")


@lru_cache
def load_logger_config() -> LoggerConfig:
    """Load configuration for the logger. Cached to avoid repeated validation.

    Returns:
        LoggerConfig: Configuration for the logger.
    """
    return LoggerConfig()
