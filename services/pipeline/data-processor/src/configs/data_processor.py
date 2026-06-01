from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

_CONFIG_FILE = Path("config_data_processor.yml")


class DataProcessorConfig(BaseModel):
    """Configuration for the data processor service."""

    # Service settings
    enabled: bool = True

    # Polling settings
    poll_interval_seconds: int = 5
    episode_limit_per_poll: int = 5

    # File paths
    raw_data_path: str = "/workspace/data/raw_episodes"
    processed_data_path: str = "/workspace/data/processed_episodes"

    # AV1 encoding settings (libsvtav1)
    av1_preset: int = 8  # 0-12, lower=slower/better (8=balanced)
    av1_gop_size: int = 2  # Keyframe frequency (2=LeRobot standard)
    av1_pixel_format: str = "yuv420p"  # Color format
    av1_threads: int = 0  # 0=auto-detect (quarter of available CPU cores)

    # Deletion flags
    # If True, delete raw (original) episode data after conversion succeeds.
    delete_raw_episode: bool = True

    @classmethod
    def from_yaml(cls, file_path: Path = _CONFIG_FILE) -> "DataProcessorConfig":
        """Load DataProcessorConfig from the data_processor section of a YAML file.

        Args:
            file_path: Path to the YAML configuration file. Defaults to
                'config_data_processor.yml'.

        Returns:
            A DataProcessorConfig instance loaded from the YAML file.
        """
        with open(file_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return cls.model_validate(raw.get("data_processor", raw))


@lru_cache
def load_data_processor_config() -> DataProcessorConfig:
    """Load configuration for the data processor.

    Cached to avoid repeated validation.
    """
    return DataProcessorConfig.from_yaml()
