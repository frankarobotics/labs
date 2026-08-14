from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

_CONFIG_FILE = Path(os.getenv("DATA_RECORDER_CONFIG_FILE", "/workspace/config_data_recorder.yml"))


class DataRecorderConfig(BaseModel):
    """Configuration for data recorder."""

    # rejects any other fields (e.g. the deprecated ros_topics)
    model_config = ConfigDict(extra="forbid")

    url: str = "0.0.0.0:3002"
    output_path: str = "/workspace/data/raw_episodes"

    @classmethod
    def from_yaml(cls, file_path: Path = _CONFIG_FILE) -> DataRecorderConfig:
        """Load DataRecorderConfig from a YAML file."""
        with open(file_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        # an empty file yields None, which should mean "all defaults"
        return cls.model_validate(raw or {})


@lru_cache
def load_data_recorder_config() -> DataRecorderConfig:
    """Load configuration for the data recorder. Cached to avoid repeated validation.

    Returns:
        DataRecorderConfig: Configuration for the data recorder.
    """
    return DataRecorderConfig.from_yaml() if _CONFIG_FILE.exists() else DataRecorderConfig()
