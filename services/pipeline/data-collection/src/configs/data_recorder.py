import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

_CONFIG_FILE = Path(os.getenv("DATA_COLLECTION_CONFIG_FILE", "/workspace/config_data_collection.yml"))


class DataRecorderConfig(BaseModel):
    """Client configuration for connecting to the data recorder service."""

    url: str = "http://localhost:3002"
    request_timeout: float = 30.0

    @classmethod
    def from_yaml(cls, file_path: Path = _CONFIG_FILE) -> "DataRecorderConfig":
        """Load DataRecorderConfig from the data_recorder section of a YAML file."""
        with open(file_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return cls.model_validate(raw.get("data_recorder", raw))


@lru_cache
def load_data_recorder_config() -> DataRecorderConfig:
    """Load configuration for the data recorder. Cached to avoid repeated validation.

    Returns:
        DataRecorderConfig: Configuration for the data recorder.
    """
    return DataRecorderConfig.from_yaml() if _CONFIG_FILE.exists() else DataRecorderConfig()
