from pydantic import BaseModel


class CompressedVideoInfo(BaseModel):
    """Model representing compressed video information.

    Attributes:
        timestamp_ns (int): The timestamp of the video in epoch nanoseconds.
        publish_time_ns (int): The time the video was published in epoch nanoseconds.
        format (str): The format of the video (e.g., "mp4").
        data (bytes): The actual video bytes.
    """

    timestamp_ns: int
    publish_time_ns: int
    format: str
    data: bytes
