"""Remote annotation operations the job service depends on, free of SDK response shapes."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

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


@dataclass(frozen=True)
class AccountCheck:
    """What Nomadic reports for an API key: the account it belongs to."""

    email: str | None


class InvalidApiKeyError(ValueError):
    """Nomadic rejected the API key."""


class RemoteFailedError(Exception):
    """Nomadic finished a step and reported that it failed, so no remote work for it is still running."""


BillingReason = Literal["out_of_credits", "uploads_not_enabled"]


class BillingDeclinedError(Exception):
    """Nomadic declined an upload or annotation for billing reasons, before starting or charging any work."""

    def __init__(self, reason: BillingReason, available: float | None = None, required: float | None = None) -> None:
        """Keep the account's balance and the cost, when Nomadic reported them."""
        super().__init__(reason)
        self.reason: BillingReason = reason
        self.available = available
        self.required = required


class AnnotationGateway(Protocol):
    """One remote session; any call may raise, and the service maps failures by stage."""

    def upload(self, path: str) -> str:
        """Return the ingest identifier of the uploaded recording."""
        ...

    def ingest(self, ingest_id: str) -> str:
        """Wait for ingestion and return the primary video identifier."""
        ...

    def start_index(self, video_id: str) -> IndexResult:
        """Start action indexing for one video and return its run reference without waiting for the result."""
        ...

    def wait_index(self, video_id: str, run_id: str) -> IndexResult:
        """Wait for a started indexing run; an incomplete result means it may still be running."""
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


GatewayFactory = Callable[[AnnotationConfig, str], AnnotationGateway]
KeyVerifier = Callable[[AnnotationConfig, str], AccountCheck]
