from typing import Any

import pytest
from pipeline_configs import CameraSegment

from lerobot_conversion.lerobot_converter import _check_camera_geometry, _validate_camera_shapes


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
