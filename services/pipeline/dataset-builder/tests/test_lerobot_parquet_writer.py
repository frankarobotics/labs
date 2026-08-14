from pathlib import Path

import numpy as np
from pipeline_configs import PolicyContract

from lerobot_conversion.lerobot_parquet_writer import LeRobotParquetWriter
from models.observation import Observation
from models.observation_action import ObservationAction
from models.observation_state import ObservationState

STATE_VALUES = {
    "arm_position": [1.0, 2.0],
    "arm_velocity": [10.0, 20.0],
    "arm_wrench": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
}
ACTION_VALUES = {"arm": [7.0, 8.0], "gripper": [0.5]}


def _observation(frame_index: int = 0) -> Observation:
    return Observation(
        timestamp_ns=frame_index * 50_000_000,
        frame_index=frame_index,
        episode_index=0,
        image={},
        state={
            key: ObservationState(timestamp_ns=0, values=values, names=[])
            for key, values in reversed(list(STATE_VALUES.items()))
        },
        action={
            key: ObservationAction(timestamp_ns=0, values=values, names=[])
            for key, values in reversed(list(ACTION_VALUES.items()))
        },
    )


def _writer(tmp_path: Path, contract: PolicyContract) -> LeRobotParquetWriter:
    return LeRobotParquetWriter(tmp_path, contract)


def test_flat_vectors_follow_the_contract_not_the_extraction_order(tmp_path: Path, contract: PolicyContract) -> None:
    writer = _writer(tmp_path, contract)

    row = writer._create_parquet_row(_observation(), episode_index=0, frame_index=0, total_frames=2)

    assert list(row["observation.state"]) == [1.0, 2.0, 10.0, 20.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    assert list(row["action"]) == [7.0, 8.0, 0.5]


def test_flat_vector_widths_match_the_contract_slices(tmp_path: Path, contract: PolicyContract) -> None:
    row = _writer(tmp_path, contract)._create_parquet_row(_observation(), 0, 0, 2)

    assert len(row["observation.state"]) == contract.state_width
    assert len(row["action"]) == contract.action_width
    for policy_key, span in contract.state_slices.items():
        assert list(row["observation.state"][span]) == STATE_VALUES[policy_key]


def test_each_state_segment_gets_its_own_column(tmp_path: Path, contract: PolicyContract) -> None:
    row = _writer(tmp_path, contract)._create_parquet_row(_observation(), 0, 0, 2)

    assert list(row["observation.state.arm_position"]) == [1.0, 2.0]
    assert list(row["observation.state.arm_velocity"]) == [10.0, 20.0]


def test_columns_use_the_contract_dtype(tmp_path: Path, contract: PolicyContract) -> None:
    row = _writer(tmp_path, contract)._create_parquet_row(_observation(), 0, 0, 2)

    assert row["observation.state"].dtype == np.float32
    assert row["action"].dtype == np.float32


def test_annotation_columns_come_from_the_contract(tmp_path: Path, contract: PolicyContract) -> None:
    row = _writer(tmp_path, contract)._create_parquet_row(_observation(), 0, 0, 2, task_index=4)

    # original_key: task_index, so the annotation follows the episode's task
    assert row["annotation.human.action.task_description"] == 4
    assert row["annotation.human.validity"] == 1


def test_every_frame_carries_its_episode_task_index(tmp_path: Path, contract: PolicyContract) -> None:
    writer = _writer(tmp_path, contract)

    row = writer._create_parquet_row(_observation(), 0, 0, 2, task_index=2)

    assert row["task_index"] == 2


def test_only_the_last_frame_is_done(tmp_path: Path, contract: PolicyContract) -> None:
    writer = _writer(tmp_path, contract)

    assert writer._create_parquet_row(_observation(0), 0, 0, 2)["next.done"] is False
    assert writer._create_parquet_row(_observation(1), 0, 1, 2)["next.done"] is True


def test_episode_is_written_with_one_row_per_observation(tmp_path: Path, contract: PolicyContract) -> None:
    writer = _writer(tmp_path, contract)

    metadata = writer.write_episode_data([_observation(0), _observation(1)], episode_index=3, chunk_index=0)

    assert metadata.frame_count == 2
    assert (tmp_path / "data/chunk-000/episode_000003.parquet").exists()
    assert metadata.parquet_file == "data/chunk-000/episode_000003.parquet"
