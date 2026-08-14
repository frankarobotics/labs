from typing import Any

from pydantic import BaseModel

from models.compressed_video_info import CompressedVideoInfo
from models.mcap_summary import McapSummary
from models.robot_action import RobotAction
from models.robot_state import RobotState
from models.topic_statistics import TopicStatistics


class ExtractedMcapData(BaseModel):
    """Data extracted from one MCAP episode, keyed by the policy_key each contract segment owns.

    Attributes:
        compressed_videos (dict[str, CompressedVideoInfo]): Compressed video per camera.
        video_stats (dict[str, TopicStatistics]): Timing statistics per camera.
        robot_states (dict[str, list[RobotState]]): Decoded values per state segment.
        state_stats (dict[str, TopicStatistics]): Timing statistics per state segment.
        actions (dict[str, list[RobotAction]]): Decoded values per action segment.
        action_stats (dict[str, TopicStatistics]): Timing statistics per action segment.
        metadata (dict[str, Any]): Arbitrary metadata associated with the MCAP extraction.
        mcap_summary (McapSummary): Summary information about the MCAP file.
    """

    compressed_videos: dict[str, CompressedVideoInfo]
    video_stats: dict[str, TopicStatistics]
    robot_states: dict[str, list[RobotState]]
    state_stats: dict[str, TopicStatistics]
    actions: dict[str, list[RobotAction]]
    action_stats: dict[str, TopicStatistics]
    metadata: dict[str, Any]
    mcap_summary: McapSummary

    class Config:  # noqa: D106
        arbitrary_types_allowed = True
