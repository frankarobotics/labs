from cv2.typing import MatLike
from pydantic import BaseModel


class ObservationImage(BaseModel):
    """Represents an observation image with associated metadata.

    Attributes:
        image (MatLike): The image data.
        width (int): Image width in pixels.
        height (int): Image height in pixels.
        original_timestamp_ns (int): Original timestamp in epoch nanoseconds.
        sync_timestamp_ns (int): Synchronized timestamp in epoch nanoseconds.
        time_diff_ms (float): Difference between original and sync timestamp in milliseconds.
    """

    image: MatLike
    width: int
    height: int
    original_timestamp_ns: int
    sync_timestamp_ns: int
    time_diff_ms: float

    class Config:  # noqa: D106
        arbitrary_types_allowed = True
