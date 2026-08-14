"""Domain model for modality.json, the layout GR00T reads the flat vectors with."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StateSegment:
    """A named segment of the concatenated observation.state vector."""

    name: str
    start: int
    end: int

    @property
    def size(self) -> int:
        """Return the number of dimensions in this segment."""
        return self.end - self.start


@dataclass(frozen=True)
class ActionSegment:
    """A named segment of the action vector."""

    name: str
    start: int
    end: int

    @property
    def size(self) -> int:
        """Return the number of dimensions in this segment."""
        return self.end - self.start


@dataclass(frozen=True)
class VideoModalityEntry:
    """Modality entry for a video stream."""

    key: str
    original_key: str


@dataclass(frozen=True)
class AnnotationEntry:
    """Modality entry for an annotation feature."""

    key: str
    # original_key, if set, means the column is copied from an existing parquet column
    original_key: str | None = None


@dataclass(frozen=True)
class ModalityConfig:
    """The modality layout dataset-builder generates from a policy contract."""

    state_segments: tuple[StateSegment, ...]
    action_segments: tuple[ActionSegment, ...]
    video_entries: tuple[VideoModalityEntry, ...]
    annotation_entries: tuple[AnnotationEntry, ...]

    @property
    def total_state_dims(self) -> int:
        """Return the total number of state dimensions."""
        if not self.state_segments:
            return 0
        return max(seg.end for seg in self.state_segments)

    @property
    def total_action_dims(self) -> int:
        """Return the total number of action dimensions."""
        if not self.action_segments:
            return 0
        return max(seg.end for seg in self.action_segments)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the modality.json wire format."""
        return {
            "state": {seg.name: {"start": seg.start, "end": seg.end} for seg in self.state_segments},
            "action": {seg.name: {"start": seg.start, "end": seg.end} for seg in self.action_segments},
            "video": {e.key: {"original_key": e.original_key} for e in self.video_entries},
            "annotation": {
                e.key: ({"original_key": e.original_key} if e.original_key else {}) for e in self.annotation_entries
            },
        }
