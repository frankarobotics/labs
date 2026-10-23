from typing import Any

import numpy as np
import pytest
from pipeline_configs import Annotation, PolicyContract

from lerobot_conversion.lerobot_frames import LeRobotFrameBuilder
from models.observation import Observation
from models.observation_action import ObservationAction
from models.observation_image import ObservationImage
from models.observation_state import ObservationState

STATE_VALUES = {
    "arm_position": [1.0, 2.0],
    "arm_velocity": [10.0, 20.0],
    "arm_wrench": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
}
ACTION_VALUES = {"arm": [7.0, 8.0], "gripper": [0.5]}


def _image(value: int) -> ObservationImage:
    return ObservationImage(
        image=np.full((4, 6, 3), value, dtype=np.uint8),
        width=6,
        height=4,
        original_timestamp_ns=0,
        sync_timestamp_ns=0,
        time_diff_ms=0.0,
    )


def _observation() -> Observation:
    return Observation(
        timestamp_ns=0,
        frame_index=0,
        episode_index=0,
        image={"head": _image(10), "wrist": _image(20)},
        state={
            key: ObservationState(timestamp_ns=0, values=values, names=[])
            for key, values in reversed(list(STATE_VALUES.items()))
        },
        action={
            key: ObservationAction(timestamp_ns=0, values=values, names=[])
            for key, values in reversed(list(ACTION_VALUES.items()))
        },
    )


def _frame(contract: PolicyContract, *, is_last_frame: bool = False, task_index: int = 0) -> dict[str, Any]:
    return LeRobotFrameBuilder(contract).build(
        _observation(), is_last_frame=is_last_frame, task="Pick", task_index=task_index
    )


def test_flat_vectors_follow_the_contract_not_the_extraction_order(contract: PolicyContract) -> None:
    frame = _frame(contract)

    assert list(frame["observation.state"]) == pytest.approx([1.0, 2.0, 10.0, 20.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    assert list(frame["action"]) == [7.0, 8.0, 0.5]


def test_flat_vector_widths_match_the_contract_slices(contract: PolicyContract) -> None:
    frame = _frame(contract)

    assert frame["observation.state"].shape == (contract.state_width,)
    assert frame["action"].shape == (contract.action_width,)
    for policy_key, span in contract.state_slices.items():
        assert list(frame["observation.state"][span]) == pytest.approx(STATE_VALUES[policy_key])


def test_each_state_segment_gets_its_own_column(contract: PolicyContract) -> None:
    frame = _frame(contract)

    assert list(frame["observation.state.arm_position"]) == [1.0, 2.0]
    assert list(frame["observation.state.arm_velocity"]) == [10.0, 20.0]


def test_columns_use_the_contract_dtype(contract: PolicyContract) -> None:
    frame = _frame(contract)

    assert frame["observation.state"].dtype == np.float32
    assert frame["action"].dtype == np.float32
    assert frame["observation.state.arm_wrench"].dtype == np.float32


def test_annotation_columns_come_from_the_contract(contract: PolicyContract) -> None:
    frame = _frame(contract, task_index=4)

    # original_key: task_index, so the annotation follows the episode's task
    assert frame["annotation.human.action.task_description"].tolist() == [4]
    assert frame["annotation.human.validity"].tolist() == [1]


def test_only_the_last_frame_is_done(contract: PolicyContract) -> None:
    assert _frame(contract)["next.done"].tolist() == [False]
    assert _frame(contract, is_last_frame=True)["next.done"].tolist() == [True]
    assert _frame(contract, is_last_frame=True)["next.reward"].tolist() == [1.0]


def test_cameras_are_keyed_by_their_dataset_feature_name(contract: PolicyContract) -> None:
    frame = _frame(contract)

    assert int(frame["observation.images.head"][0, 0, 0]) == 10
    assert int(frame["observation.images.wrist"][0, 0, 0]) == 20
    assert frame["task"] == "Pick"


def test_annotation_copying_a_column_lerobot_fills_later_is_rejected(contract: PolicyContract) -> None:
    copying_frame_index = contract.model_copy(
        update={"annotations": (Annotation(policy_key="human.step", original_key="frame_index"),)}
    )

    with pytest.raises(ValueError, match=r"unsupported columns: human\.step <- frame_index"):
        LeRobotFrameBuilder(copying_frame_index)
