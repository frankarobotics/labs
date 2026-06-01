from typing import Any

from pydantic import BaseModel


class Feature(BaseModel):
    """Represents a generic feature with type, shape, and optional names.

    Attributes:
        dtype: The data type of the feature.
        shape: The shape of the feature as a tuple of integers.
        names: Optional names for the feature.
    """

    dtype: str
    shape: tuple[int, ...]
    names: None | list[str] | dict[str, list[str]]

    def to_dict(self) -> dict[str, Any]:  # noqa: D102
        return self.model_dump()


class VideoFeature(Feature):
    """Represents a video feature with specific metadata.

    Attributes:
        dtype: The type of feature, set to "video".
        video_info: Metadata and information about the video.
    """

    dtype: str = "video"
    video_info: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:  # noqa: D102
        return self.model_dump()
