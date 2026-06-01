from mcap.records import Statistics
from pydantic import BaseModel

from models.topic_info import TopicInfo


class McapSummary(BaseModel):
    """Summary of MCAP file contents.

    Attributes:
        topics (dict[str, TopicInfo]): Mapping of topic names to their information.
        statistics (Statistics | None): Optional MCAP file statistics.
    """

    topics: dict[str, TopicInfo]
    statistics: Statistics | None

    class Config:  # noqa: D106
        arbitrary_types_allowed = True
