from typing import Any

from pydantic import BaseModel

from models.compressed_video_info import CompressedVideoInfo
from models.mcap_summary import McapSummary
from models.robot_action import RobotAction
from models.robot_state import RobotState
from models.topic_statistics import TopicStatistics


class ExtractedMcapData(BaseModel):
    """Represents extracted MCAP data including videos, robot states, actions, metadata, and summary.

    Attributes:
        compressed_videos (dict[str, CompressedVideoInfo]): Mapping of video topics to compressed video info.
        video_topics (dict[str, TopicStatistics]): Mapping of video topics to their statistics.
        robot_states (dict[str, list[RobotState]]): Mapping of robot state topics to lists of robot states.
        robot_state_topics (dict[str, TopicStatistics]): Mapping of robot state topics to their statistics.
        actions (dict[str, list[RobotAction]]): Mapping of robot action topics to lists of robot actions.
        action_topics (dict[str, TopicStatistics]): Mapping of robot action topics to their statistics.
        metadata (dict[str, Any]): Arbitrary metadata associated with the MCAP extraction.
        mcap_summary (McapSummary): Summary information about the MCAP file.
    """

    compressed_videos: dict[str, CompressedVideoInfo]
    video_topics: dict[str, TopicStatistics]
    robot_states: dict[str, list[RobotState]]
    robot_state_topics: dict[str, TopicStatistics]
    actions: dict[str, list[RobotAction]]
    action_topics: dict[str, TopicStatistics]
    metadata: dict[str, Any]
    mcap_summary: McapSummary

    class Config:  # noqa: D106
        arbitrary_types_allowed = True
