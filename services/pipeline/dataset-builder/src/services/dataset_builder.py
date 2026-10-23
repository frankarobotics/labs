"""Dataset build orchestration and format registry."""

from collections.abc import Callable
from importlib import import_module
from typing import Any

from models.dataset_build_request import DatasetBuildRequest

DatasetBuilder = Callable[[DatasetBuildRequest], dict[str, Any]]
DatasetBuilderLoader = Callable[[], DatasetBuilder]


class UnsupportedDatasetFormatError(ValueError):
    """Raised when a dataset format is not registered."""


def _load_lerobot_builder() -> DatasetBuilder:
    module = import_module("lerobot_conversion.lerobot_converter")
    builder: DatasetBuilder = module.convert_mcaps_to_lerobot
    return builder


BUILDERS: dict[str, DatasetBuilderLoader] = {
    "lerobot": _load_lerobot_builder,
}


def list_supported_formats() -> tuple[str, ...]:
    """Return all supported dataset formats."""
    return tuple(sorted(BUILDERS.keys()))


def build_dataset(request: DatasetBuildRequest) -> dict[str, Any]:
    """Build a dataset from one or more MCAP files."""
    builder_loader = BUILDERS.get(request.target_format)
    if builder_loader is None:
        supported_formats = ", ".join(list_supported_formats())
        raise UnsupportedDatasetFormatError(
            f"Unsupported dataset format: {request.target_format}. Supported formats: {supported_formats}"
        )

    builder = builder_loader()

    return builder(request)
