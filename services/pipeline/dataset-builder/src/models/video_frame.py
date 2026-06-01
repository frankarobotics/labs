from cv2.typing import MatLike
from pydantic import BaseModel


class VideoFrame(BaseModel):
    """Represents a single video frame with metadata and image data.

    Attributes:
        frame_index: Index of the frame in the sequence.
        timestamp_ns: Timestamp in epoch nanoseconds.
        video_frame_index: Frame index within the video stream.
        image: Image data as an opencv MatLike object.
        height: Height of the image in pixels.
        width: Width of the image in pixels.
        channels: Number of color channels in the image.
    """

    frame_index: int
    timestamp_ns: int
    video_frame_index: int
    image: MatLike
    height: int
    width: int
    channels: int

    class Config:  # noqa: D106
        arbitrary_types_allowed = True
