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
