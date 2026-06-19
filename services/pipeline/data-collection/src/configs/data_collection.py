import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

_CONFIG_FILE = Path(os.getenv("DATA_COLLECTION_CONFIG_FILE", "/workspace/config_data_collection.yml"))


class DataCollectionConfig(BaseModel):
    """Configuration for data collection."""

    url: str = "0.0.0.0:3001"
    device_status_poll_interval_sec: float = 0.5
    processed_data_path: str = "/workspace/data/processed_episodes"

    @classmethod
    def from_yaml(cls, file_path: Path = _CONFIG_FILE) -> "DataCollectionConfig":
        """Load DataCollectionConfig from the data_collection section of a YAML file."""
        with open(file_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return cls.model_validate(raw.get("data_collection", raw))


@lru_cache
def load_data_collection_config() -> DataCollectionConfig:
    """Load configuration for the data collection. Cached to avoid repeated validation.

    Returns:
        DataCollectionConfig: Configuration for the data collection.
    """
    return DataCollectionConfig.from_yaml() if _CONFIG_FILE.exists() else DataCollectionConfig()
