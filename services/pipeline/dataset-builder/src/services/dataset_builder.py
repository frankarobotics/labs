"""Dataset build orchestration and format registry."""

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

DatasetBuilder = Callable[..., dict[str, Any]]
DatasetBuilderLoader = Callable[[], DatasetBuilder]


class UnsupportedDatasetFormatError(ValueError):
    """Raised when a dataset format is not registered."""


@dataclass(frozen=True)
class SingleDatasetBuildRequest:
    """Input required to build a dataset from a single MCAP file."""

    input_path: Path
    output_dir: Path
    target_format: str
    target_fps: float
    dataset_name: str
    station_config_path: Path | None = None
    recorder_config_path: Path | None = None
    modality_config_path: Path | None = None


def _load_lerobot_builder() -> DatasetBuilder:
    module = import_module("lerobot_conversion.lerobot_converter")
    builder: DatasetBuilder = module.convert_mcap_to_lerobot
    return builder


BUILDERS: dict[str, DatasetBuilderLoader] = {
    "lerobot": _load_lerobot_builder,
}


def list_supported_formats() -> tuple[str, ...]:
    """Return all supported dataset formats."""
    return tuple(sorted(BUILDERS.keys()))


def build_single_dataset(request: SingleDatasetBuildRequest) -> dict[str, Any]:
    """Build a dataset from a single MCAP file."""
    builder_loader = BUILDERS.get(request.target_format)
    if builder_loader is None:
        supported_formats = ", ".join(list_supported_formats())
        raise UnsupportedDatasetFormatError(
            f"Unsupported dataset format: {request.target_format}. Supported formats: {supported_formats}"
        )

    builder = builder_loader()

    return builder(
        mcap_file=request.input_path,
        output_dir=request.output_dir,
        target_fps=request.target_fps,
        dataset_name=request.dataset_name,
        station_config_path=request.station_config_path,
        recorder_config_path=request.recorder_config_path,
        modality_config_path=request.modality_config_path,
    )
