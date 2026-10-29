"""Remote annotation operations the job service depends on, free of SDK response shapes."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from configs.annotator import AnnotationConfig
from jobs.models import AnnotationEvent


@dataclass(frozen=True)
class IndexResult:
    """Remote references from one indexing run, kept even when the run did not complete."""

    completed: bool
    batch_id: str | None = None
    run_id: str | None = None
    analysis_id: str | None = None
    video_id: str | None = None
    has_warnings: bool = False


class AnnotationGateway(Protocol):
    """One remote session; any call may raise, and the service maps failures by stage."""

    def upload(self, path: str) -> str:
        """Return the ingest identifier of the uploaded recording."""
        ...

    def ingest(self, ingest_id: str) -> str:
        """Wait for ingestion and return the primary video identifier."""
        ...

    def index(self, video_id: str) -> IndexResult:
        """Run action indexing for one video."""
        ...

    def analysis_id(self, batch_id: str, video_id: str) -> str | None:
        """Resolve the video's analysis in a saved batch, if it exists yet."""
        ...

    def events(self, video_id: str, analysis_id: str) -> list[AnnotationEvent]:
        """Load a completed analysis as normalized action windows."""
        ...

    def close(self) -> None:
        """Release the session."""
        ...


GatewayFactory = Callable[[AnnotationConfig], AnnotationGateway]
