"""Round trip through LeRobot's own v3.0 writer and reader, without MCAP input."""

import copy
import json
import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml
from lerobot.datasets.lerobot_dataset import LeRobotDataset  # type: ignore[import-untyped]
from pipeline_configs import PolicyContract

from lerobot_conversion.lerobot_converter import LeRobotConverter
from lerobot_conversion.lerobot_features import build_modality_config
from models.observation import Observation
from models.observation_action import ObservationAction
from models.observation_image import ObservationImage
from models.observation_state import ObservationState

FPS = 20
HEIGHT, WIDTH = 64, 96
# distinct channel levels, so a swapped channel order shows up after the lossy encode
RGB = (200, 120, 40)
EPISODES = (("Pick the red box", 12), ("Place it on the shelf", 9))


def _observation(frame_index: int) -> Observation:
    def image(offset: int) -> ObservationImage:
        pixels = np.empty((HEIGHT, WIDTH, 3), dtype=np.uint8)
        pixels[:] = [min(255, level + offset) for level in RGB]
        return ObservationImage(
            image=pixels, width=WIDTH, height=HEIGHT, original_timestamp_ns=0, sync_timestamp_ns=0, time_diff_ms=0.0
        )

    ramp = float(frame_index)
    return Observation(
        timestamp_ns=1_700_000_000_000_000_000 + frame_index * 50_000_000,
        frame_index=frame_index,
        episode_index=0,
        image={"head": image(frame_index), "wrist": image(0)},
        state={
            "arm_position": ObservationState(timestamp_ns=0, values=[ramp, -ramp], names=[]),
            "arm_velocity": ObservationState(timestamp_ns=0, values=[1.0, 2.0 + ramp], names=[]),
            "arm_wrench": ObservationState(timestamp_ns=0, values=[ramp * 0.1] * 6, names=[]),
        },
        action={
            "arm": ObservationAction(timestamp_ns=0, values=[ramp + 0.5, -ramp], names=[]),
            "gripper": ObservationAction(timestamp_ns=0, values=[frame_index % 2], names=[]),
        },
    )


def _build(root: Path, contract_data: dict[str, Any], policy_type: str, episodes: tuple[tuple[str, int], ...]) -> Path:
    contract_data = copy.deepcopy(contract_data)
    for camera in contract_data["cameras"]:
        camera["shape"] = [HEIGHT, WIDTH, 3]
    contract_path = root / "contract.yml"
    contract_path.write_text(yaml.safe_dump(contract_data))

    output = root / "dataset"
    converter = LeRobotConverter(output, contract_path, dataset_name="labs/roundtrip", policy_type=policy_type)
    try:
        for task, length in episodes:
            converter.record_episode([_observation(i) for i in range(length)], task)
        converter.finalize_dataset()
    finally:
        converter.close()
    return output


@pytest.fixture(scope="module")
def dataset_dir(tmp_path_factory: pytest.TempPathFactory, contract_data: dict[str, Any]) -> Iterator[Path]:
    yield _build(tmp_path_factory.mktemp("build"), contract_data, "gr00t", EPISODES)


def _meta(dataset_dir: Path, name: str) -> Any:  # noqa: ANN401 - JSON document
    return json.loads((dataset_dir / "meta" / name).read_text())


def _episodes(dataset_dir: Path) -> pd.DataFrame:
    files = sorted((dataset_dir / "meta/episodes").glob("*/*.parquet"))
    return pd.concat([pd.read_parquet(path) for path in files]).sort_values("episode_index")


def test_info_declares_v3_and_counts_every_episode(dataset_dir: Path) -> None:
    info = _meta(dataset_dir, "info.json")

    assert info["codebase_version"] == "v3.0"
    assert info["fps"] == FPS
    assert info["total_episodes"] == len(EPISODES)
    assert info["total_frames"] == sum(length for _, length in EPISODES)
    assert info["total_tasks"] == len(EPISODES)


def test_encoded_video_geometry_is_recorded_per_camera(dataset_dir: Path) -> None:
    features = _meta(dataset_dir, "info.json")["features"]

    for key in ("observation.images.head", "observation.images.wrist"):
        encoded = features[key]["info"]
        assert (encoded["video.height"], encoded["video.width"], encoded["video.channels"]) == (HEIGHT, WIDTH, 3)
        assert encoded["video.codec"] == "av1"


def test_every_episode_references_existing_data_and_video_files(dataset_dir: Path) -> None:
    info = _meta(dataset_dir, "info.json")
    episodes = _episodes(dataset_dir)

    assert episodes["episode_index"].tolist() == list(range(len(EPISODES)))
    assert episodes["length"].tolist() == [length for _, length in EPISODES]
    for _, row in episodes.iterrows():
        data = info["data_path"].format(chunk_index=row["data/chunk_index"], file_index=row["data/file_index"])
        assert (dataset_dir / data).stat().st_size > 0
        for key in ("observation.images.head", "observation.images.wrist"):
            video = info["video_path"].format(
                video_key=key,
                chunk_index=row[f"videos/{key}/chunk_index"],
                file_index=row[f"videos/{key}/file_index"],
            )
            assert (dataset_dir / video).stat().st_size > 0


@pytest.mark.parametrize("feature", ["observation.state", "action"])
def test_stats_carry_finite_quantiles_with_real_spread(dataset_dir: Path, feature: str) -> None:
    """pi0.5's QUANTILES normalization needs q01/q99, and a zero-filled placeholder has min == max."""
    stats = _meta(dataset_dir, "stats.json")[feature]

    for key in ("min", "max", "mean", "std", "q01", "q99"):
        assert all(math.isfinite(value) for value in stats[key]), key
    assert stats["min"] != stats["max"]
    assert stats["count"] == [sum(length for _, length in EPISODES)]


def test_timestamps_follow_the_frame_index(dataset_dir: Path) -> None:
    frames = pd.read_parquet(dataset_dir / "data")

    np.testing.assert_allclose(frames["timestamp"], frames["frame_index"] / FPS, atol=1e-6)


def test_task_annotation_matches_the_task_index_lerobot_recorded(dataset_dir: Path) -> None:
    frames = pd.read_parquet(dataset_dir / "data")
    tasks = pd.read_parquet(dataset_dir / "meta/tasks.parquet")

    assert (frames["annotation.human.action.task_description"] == frames["task_index"]).all()
    assert sorted(tasks["task_index"].tolist()) == [0, 1]
    assert frames.groupby("episode_index")["task_index"].unique().map(len).eq(1).all()


def test_modality_json_is_derived_from_the_contract(dataset_dir: Path, contract: PolicyContract) -> None:
    assert _meta(dataset_dir, "modality.json") == build_modality_config(contract).to_dict()


def test_modality_json_is_written_for_gr00t_only(tmp_path: Path, contract_data: dict[str, Any]) -> None:
    dataset = _build(tmp_path, contract_data, "pi05", (("Pick", 2),))

    assert (dataset / "meta/info.json").exists()
    assert not (dataset / "meta/modality.json").exists()


def test_lerobot_reads_back_the_recorded_vectors_and_colours(dataset_dir: Path) -> None:
    dataset = LeRobotDataset("labs/roundtrip", root=dataset_dir)
    last_of_first_episode = EPISODES[0][1] - 1

    item = dataset[last_of_first_episode]

    expected = _observation(last_of_first_episode)
    np.testing.assert_allclose(item["action"].numpy(), [last_of_first_episode + 0.5, -last_of_first_episode, 1.0])
    assert item["observation.state"].numpy()[:2].tolist() == [last_of_first_episode, -last_of_first_episode]
    decoded = item["observation.images.wrist"].numpy()
    assert decoded.shape == (3, HEIGHT, WIDTH)
    written = expected.image["wrist"].image
    for channel in range(3):
        assert decoded[channel].mean() * 255 == pytest.approx(written[..., channel].mean(), abs=6)
