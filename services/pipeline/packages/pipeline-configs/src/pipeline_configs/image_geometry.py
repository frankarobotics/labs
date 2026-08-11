"""Shared image fitting geometry for train and serve transforms."""

from __future__ import annotations

from dataclasses import dataclass

PAD_VALUE = 0
PADDING_WARN_FRACTION = 0.01


@dataclass(frozen=True)
class LetterboxGeometry:
    """Describe a scaled source frame centred inside a target geometry."""

    width: int
    height: int
    left: int
    top: int
    target_width: int
    target_height: int

    @property
    def right(self) -> int:
        """Return padding columns right of the scaled frame."""
        return self.target_width - self.width - self.left

    @property
    def bottom(self) -> int:
        """Return padding rows below the scaled frame."""
        return self.target_height - self.height - self.top

    @property
    def is_padded(self) -> bool:
        """Return whether the fit leaves any padding."""
        return (self.height, self.width) != (self.target_height, self.target_width)

    @property
    def padding_fraction(self) -> float:
        """Return the share of target pixels occupied by padding."""
        return 1.0 - (self.width * self.height) / (self.target_width * self.target_height)


def compute_letterbox_geometry(source_shape: tuple[int, int], target_shape: tuple[int, int]) -> LetterboxGeometry:
    """Fit a source shape inside a target shape without changing its aspect ratio."""
    source_height, source_width = source_shape
    target_height, target_width = target_shape
    if min(source_height, source_width, target_height, target_width) <= 0:
        raise ValueError("source and target dimensions must be positive")

    if source_width * target_height >= source_height * target_width:
        width = target_width
        height = _div_round(source_height * target_width, source_width)
    else:
        height = target_height
        width = _div_round(source_width * target_height, source_height)

    height, width = max(1, height), max(1, width)
    return LetterboxGeometry(
        width=width,
        height=height,
        left=(target_width - width) // 2,
        top=(target_height - height) // 2,
        target_width=target_width,
        target_height=target_height,
    )


def _div_round(numerator: int, denominator: int) -> int:
    """Return round-half-up integer division."""
    return (numerator + denominator // 2) // denominator
