"""Translation of one synchronized observation into the frame LeRobot's dataset writer records."""

from typing import Any

import numpy as np
from pipeline_configs import PolicyContract

from lerobot_conversion.lerobot_utils import get_annotation_feature_name, get_observation_state_feature_name
from models.observation import Observation

# annotation columns are indices into an external table, never policy values
ANNOTATION_DTYPE = np.int64
# an annotation without an original_key to copy is a flag dataset-builder asserts (human.validity)
DEFAULT_ANNOTATION_VALUE = 1
# LeRobot fills every other index column itself, after the frame is recorded
_COPYABLE_ANNOTATION_SOURCES = frozenset({"task_index"})


class LeRobotFrameBuilder:
    """Build ``LeRobotDataset.add_frame`` input in the contract's column layout."""

    def __init__(self, contract: PolicyContract) -> None:
        """Initialize the frame builder.

        Args:
            contract: Policy contract defining column order, layout and dtype
        """
        unsupported = sorted(
            f"{annotation.policy_key} <- {annotation.original_key}"
            for annotation in contract.annotations
            if annotation.original_key is not None and annotation.original_key not in _COPYABLE_ANNOTATION_SOURCES
        )
        if unsupported:
            raise ValueError(
                f"Annotations copy from unsupported columns: {', '.join(unsupported)}; "
                f"supported: {', '.join(sorted(_COPYABLE_ANNOTATION_SOURCES))}"
            )
        self.contract = contract

    def build(self, observation: Observation, *, is_last_frame: bool, task: str, task_index: int) -> dict[str, Any]:
        """Create one frame from a synchronized observation.

        Args:
            observation: Synchronized observation data
            is_last_frame: Whether this is the episode's final frame
            task: The episode's task description
            task_index: Index LeRobot assigns ``task`` in meta/tasks.parquet

        Returns:
            Frame dictionary keyed by LeRobot feature name, plus ``task``
        """
        # the contract concatenates in declaration order, not extraction order, so its slices index these vectors
        flat_state = self.contract.flatten_state({key: state.values for key, state in observation.state.items()})
        frame: dict[str, Any] = {
            get_observation_state_feature_name(policy_key): flat_state[span]
            for policy_key, span in self.contract.state_slices.items()
        }
        frame["observation.state"] = flat_state
        frame["action"] = self.contract.flatten_action(
            {key: action.values for key, action in observation.action.items()}
        )

        frame["next.reward"] = np.array([is_last_frame], dtype=np.float32)
        frame["next.done"] = np.array([is_last_frame], dtype=np.bool_)

        for annotation in self.contract.annotations:
            value = task_index if annotation.original_key is not None else DEFAULT_ANNOTATION_VALUE
            frame[get_annotation_feature_name(annotation.policy_key)] = np.array([value], dtype=ANNOTATION_DTYPE)

        for camera in self.contract.cameras:
            frame[camera.dataset_feature_name] = observation.image[camera.policy_key].image

        frame["task"] = task
        return frame
