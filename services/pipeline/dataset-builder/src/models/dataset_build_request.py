from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatasetBuildRequest:
    """Input required to build a dataset from one or more MCAP files."""

    mcap_files: tuple[Path, ...]
    output_dir: Path
    target_format: str
    dataset_name: str
    policy_contract_path: Path
    policy_type: str
    target_fps: int | None = None
