"""Server-only configuration for Nomadic annotations."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from configs.data_collection import load_data_collection_config


class AnnotationConfig(BaseSettings):
    """Load optional integration settings from NOMADIC_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="NOMADIC_", env_ignore_empty=True, extra="ignore")

    enabled: bool = False
    api_key: SecretStr = SecretStr("")
    base_url: str = "https://api-prod.nomadicml.com"
    dashboard_url: str = "https://app.nomadicml.com"
    folder: str = "Franka LABS"
    processed_episodes_path: Path = Path("/workspace/data/processed_episodes")
    state_path: Path = Path("/workspace/data/nomadic_annotations")
    spec_path: Path | None = None
    policy_contract_path: Path | None = None
    timeout_seconds: int = Field(default=3600, ge=1, le=86400)
    max_pending_jobs: int = Field(default=4, ge=1, le=16)
    max_recording_bytes: int = Field(default=4 * 1024**3, ge=1)


@lru_cache
def get_annotation_config() -> AnnotationConfig:
    """Read configuration once; credentials never enter API response models."""
    config = AnnotationConfig()
    if "processed_episodes_path" not in config.model_fields_set:
        config.processed_episodes_path = Path(load_data_collection_config().processed_data_path)
    if "state_path" not in config.model_fields_set:
        config.state_path = config.processed_episodes_path.parent / "nomadic_annotations"
    return config
