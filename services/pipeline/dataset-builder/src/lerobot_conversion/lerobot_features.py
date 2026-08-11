"""Translation of a policy contract into the LeRobot metadata it describes: info.json features and modality.json."""

from typing import Any

from lerobot.datasets.utils import DEFAULT_FEATURES  # type: ignore[import-not-found]
from pipeline_configs import PolicyContract, PolicySegment

from lerobot_conversion.lerobot_utils import (
    get_annotation_feature_name,
    get_observation_state_feature_name,
    get_video_feature_name,
)
from models.feature import Feature, VideoFeature
from models.modality_config import (
    ActionSegment,
    AnnotationEntry,
    ModalityConfig,
    StateSegment,
    VideoModalityEntry,
)


def build_features(contract: PolicyContract, video_infos: dict[str, dict[str, Any]]) -> dict[str, Feature]:
    """Describe every Parquet and video column the contract produces, for info.json.

    Args:
        contract: The policy contract defining the state/action layout and cameras.
        video_infos: Encoded video metadata (codec, geometry) per camera policy key.

    Returns:
        Feature definitions keyed by LeRobot feature name.
    """
    dtype = contract.policy.dtype
    features: dict[str, Feature] = {
        name: Feature(dtype=spec["dtype"], shape=spec["shape"], names=spec["names"])
        for name, spec in DEFAULT_FEATURES.items()
    }

    for policy_key, video_info in video_infos.items():
        features[get_video_feature_name(policy_key)] = VideoFeature(
            names=["height", "width", "channels"],
            shape=(video_info["video.height"], video_info["video.width"], video_info["video.channels"]),
            video_info=video_info,
        )

    for segment in contract.state:
        features[get_observation_state_feature_name(segment.policy_key)] = Feature(
            dtype=dtype, shape=(segment.width,), names=list(segment.element_names)
        )

    features["observation.state"] = Feature(
        dtype=dtype, shape=(contract.state_width,), names=_flat_names(contract.state)
    )
    features["action"] = Feature(dtype=dtype, shape=(contract.action_width,), names=_flat_names(contract.action))

    features["next.reward"] = Feature(dtype="float32", shape=(1,), names=None)
    features["next.done"] = Feature(dtype="bool", shape=(1,), names=None)

    for annotation in contract.annotations:
        features[get_annotation_feature_name(annotation.policy_key)] = Feature(dtype="int64", shape=(1,), names=None)

    return features


def build_modality_config(contract: PolicyContract) -> ModalityConfig:
    """Derive meta/modality.json from the contract's flat spans, cameras and annotations."""
    return ModalityConfig(
        state_segments=tuple(
            StateSegment(name=policy_key, start=span.start, end=span.stop)
            for policy_key, span in contract.state_slices.items()
        ),
        action_segments=tuple(
            ActionSegment(name=policy_key, start=span.start, end=span.stop)
            for policy_key, span in contract.action_slices.items()
        ),
        video_entries=tuple(
            VideoModalityEntry(key=camera.policy_key, original_key=get_video_feature_name(camera.policy_key))
            for camera in contract.cameras
        ),
        annotation_entries=tuple(
            AnnotationEntry(key=annotation.policy_key, original_key=annotation.original_key)
            for annotation in contract.annotations
        ),
    )


def _flat_names(segments: tuple[PolicySegment, ...]) -> list[str]:
    """Name every element of a flat vector by the segment it came from."""
    return [f"{segment.policy_key}_{element}" for segment in segments for element in segment.element_names]
