from pydantic import BaseModel


class TopicStatistics(BaseModel):
    """Statistics for a ROS topic stream.

    Attributes:
        first_message_time_ns (int): Timestamp of the first message in epoch nanoseconds.
        last_message_time_ns (int): Timestamp of the last message in epoch nanoseconds.
        gaps (list[tuple[int, int]]): List of (start_ns, end_ns) tuples representing gaps in message timestamps.
        fps (float): Average frames per second for the topic.
        message_count (int): Total number of messages received.
    """

    first_message_time_ns: int
    last_message_time_ns: int
    gaps: list[tuple[int, int]]
    fps: float
    message_count: int
