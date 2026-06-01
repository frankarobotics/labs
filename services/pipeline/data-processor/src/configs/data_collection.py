from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

_CONFIG_FILE = Path("config_data_processor.yml")


class DataCollectionConfig(BaseModel):
    """Configuration for contacting the data-collection service."""

    url: str = "http://localhost:3001"
    request_timeout: float = 30.0

    @classmethod
    def from_yaml(cls, file_path: Path = _CONFIG_FILE) -> "DataCollectionConfig":
        """Load DataCollectionConfig from the data_collection section of a YAML file."""
        with open(file_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return cls.model_validate(raw.get("data_collection", {}))


@lru_cache
def load_data_collection_config() -> DataCollectionConfig:
    """Load configuration for the data collection client.

    Cached to avoid repeated validation.
    """
    return DataCollectionConfig.from_yaml()
