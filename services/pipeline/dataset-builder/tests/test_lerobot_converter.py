from pathlib import Path
from typing import Any

import pytest
from pipeline_configs import CameraSegment

from lerobot_conversion import lerobot_converter
from lerobot_conversion.lerobot_converter import (
    _check_camera_geometry,
    _validate_camera_shapes,
    convert_mcaps_to_lerobot,
)
from models.dataset_build_request import DatasetBuildRequest


def _camera(**overrides: object) -> CameraSegment:
    defaults: dict[str, Any] = {
        "policy_key": "head",
        "topic": "/head/camera/color/image_raw",
        "shape": [224, 224, 3],
        "resize": True,
    }
    return CameraSegment.model_validate(defaults | overrides)


def _video_info(height: int, width: int, channels: int = 3) -> dict[str, Any]:
    return {"video.height": height, "video.width": width, "video.channels": channels}


@pytest.mark.parametrize("resize", [True, False])
def test_odd_declared_shape_is_rejected(resize: bool) -> None:
    """Frames reach the yuv420p encode at ``shape`` in either mode, so odd dimensions never encode."""
    with pytest.raises(ValueError, match="odd shape"):
        _validate_camera_shapes((_camera(shape=[225, 224, 3], resize=resize),))


def test_non_three_channel_camera_is_rejected() -> None:
    with pytest.raises(ValueError, match="only 3-channel video"):
        _validate_camera_shapes((_camera(shape=[224, 224, 1]),))


@pytest.mark.parametrize("resize", [True, False])
def test_encoded_geometry_matching_the_contract_passes(resize: bool) -> None:
    _check_camera_geometry(_camera(resize=resize), _video_info(224, 224))


@pytest.mark.parametrize("resize", [True, False])
def test_encoded_geometry_differing_from_the_contract_raises(resize: bool) -> None:
    with pytest.raises(ValueError, match="were written at"):
        _check_camera_geometry(_camera(resize=resize), _video_info(480, 640))


class _CleanupFailingConverter:
    def __init__(self, *_: object) -> None:
        pass

    def convert_episode(self, _: Path) -> str:
        return "episode"

    def finalize_dataset(self) -> dict[str, Path]:
        return {"info": Path("info.json")}

    def close(self) -> None:
        raise RuntimeError("finalize failed")


class _FailingConverter(_CleanupFailingConverter):
    def convert_episode(self, _: Path) -> str:
        raise ValueError("conversion failed")


_REQUEST = DatasetBuildRequest(
    mcap_files=(Path("episode.mcap"),),
    output_dir=Path("unused"),
    target_format="lerobot",
    dataset_name="dataset",
    policy_contract_path=Path("contract.yaml"),
    policy_type="gr00t",
)


def test_a_cleanup_failure_does_not_replace_the_conversion_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lerobot_converter, "LeRobotConverter", _FailingConverter)

    with pytest.raises(ValueError, match="conversion failed"):
        convert_mcaps_to_lerobot(_REQUEST)


def test_a_cleanup_failure_does_not_fail_a_finalized_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lerobot_converter, "LeRobotConverter", _CleanupFailingConverter)

    result = convert_mcaps_to_lerobot(_REQUEST)

    assert result["metadata_files"] == {"info": Path("info.json")}
