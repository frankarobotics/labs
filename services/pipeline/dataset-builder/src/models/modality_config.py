"""Domain model for modality.json configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
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
    """Parsed representation of modality.json."""

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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModalityConfig:
        """Create a ModalityConfig from a dictionary."""
        state_segments = tuple(
            StateSegment(name=k, start=v["start"], end=v["end"]) for k, v in (data.get("state") or {}).items()
        )
        action_segments = tuple(
            ActionSegment(name=k, start=v["start"], end=v["end"]) for k, v in (data.get("action") or {}).items()
        )
        video_entries = tuple(
            VideoModalityEntry(key=k, original_key=v.get("original_key", k))
            for k, v in (data.get("video") or {}).items()
        )
        annotation_entries = tuple(
            AnnotationEntry(key=k, original_key=v.get("original_key"))
            for k, v in (data.get("annotation") or {}).items()
        )
        return cls(
            state_segments=state_segments,
            action_segments=action_segments,
            video_entries=video_entries,
            annotation_entries=annotation_entries,
        )

    @classmethod
    def from_file(cls, path: Path) -> ModalityConfig:
        """Load a ModalityConfig from a JSON file."""
        with path.open() as f:
            return cls.from_dict(json.load(f))

    def to_dict(self) -> dict[str, Any]:
        """Serialize back to the modality.json wire format."""
        return {
            "state": {seg.name: {"start": seg.start, "end": seg.end} for seg in self.state_segments},
            "action": {seg.name: {"start": seg.start, "end": seg.end} for seg in self.action_segments},
            "video": {e.key: {"original_key": e.original_key} for e in self.video_entries},
            "annotation": {
                e.key: ({"original_key": e.original_key} if e.original_key else {}) for e in self.annotation_entries
            },
        }
