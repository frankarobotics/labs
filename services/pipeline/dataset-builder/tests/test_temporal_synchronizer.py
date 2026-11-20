import pytest

from lerobot_conversion.temporal_synchronizer import TemporalSynchronizer
from models.extracted_mcap_data import ExtractedMcapData
from models.mcap_summary import McapSummary
from models.robot_action import RobotAction
from models.robot_state import RobotState
from models.topic_statistics import TopicStatistics

START_NS = 1_700_000_000_000_000_000
# 1.07 s is not a whole number of 20 Hz frames, which is what a grid stretched to the end would hide
DURATION_NS = 1_070_000_000


def _stats(duration_ns: int) -> TopicStatistics:
    return TopicStatistics(
        first_message_time_ns=START_NS,
        last_message_time_ns=START_NS + duration_ns,
        gaps=[],
        fps=100.0,
        message_count=2,
    )


def _extracted(duration_ns: int = DURATION_NS) -> ExtractedMcapData:
    ends = (START_NS, START_NS + duration_ns)
    return ExtractedMcapData(
        compressed_videos={},
        video_stats={},
        robot_states={"arm": [RobotState(timestamp_ns=t, publish_time_ns=t, values=[0.0], names=[]) for t in ends]},
        state_stats={"arm": _stats(duration_ns)},
        actions={"arm": [RobotAction(timestamp_ns=t, publish_time_ns=t, values=[0.0], names=[]) for t in ends]},
        action_stats={"arm": _stats(duration_ns)},
        metadata={},
        mcap_summary=McapSummary(topics={}, statistics=None),
    )


@pytest.mark.parametrize("fps", [20, 15])
def test_grid_steps_exactly_one_frame_interval(fps: int) -> None:
    """LeRobot stamps frame i at i / fps, so the samples must sit there rather than spread to the last message."""
    observations = TemporalSynchronizer(fps).synchronize_episode_data({}, _extracted())

    assert len(observations) == DURATION_NS * fps // 1_000_000_000 + 1
    for index, observation in enumerate(observations):
        assert observation.timestamp_ns == pytest.approx(index * 1e9 / fps, abs=1)
    assert observations[-1].timestamp_ns <= DURATION_NS


def test_a_span_of_whole_intervals_keeps_its_closing_sample() -> None:
    """1e9 // (1e9 / 7) floors to 6.0 in floats, which would drop the sample landing exactly on the last message."""
    observations = TemporalSynchronizer(7).synchronize_episode_data({}, _extracted(1_000_000_000))

    assert len(observations) == 8
    assert observations[-1].timestamp_ns == 1_000_000_000
