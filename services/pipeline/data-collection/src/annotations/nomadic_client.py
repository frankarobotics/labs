"""Nomadic SDK operations and annotation response normalization."""

import importlib
import math
from typing import Any
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid5

from annotations.config import AnnotationConfig
from annotations.models import AnnotationEvent


class NomadicGateway:
    """Own one SDK session for the lifetime of a background job."""

    def __init__(self, config: AnnotationConfig) -> None:
        """Import the optional SDK only when annotation is requested."""
        sdk = importlib.import_module("nomadic")
        self.client = sdk.NomadicAI(
            api_key=config.api_key.get_secret_value(),
            base_url=config.base_url,
            timeout=60,
        )
        self.config = config
        try:
            # An empty input validates the public mode without submitting work.
            self.client.index([], mode="robotics", timeout=1)
        except Exception as exc:
            self.client.session.close()
            raise ValueError("Install the supported Nomadic SDK with robotics indexing support.") from exc

    def upload(self, path: str) -> dict[str, Any]:
        """Return the ingest identifier before waiting for MCAP processing."""
        return dict(self.client.upload(path, folder=self.config.folder, wait_for_uploaded=False, index_data=False))

    def ingest(self, ingest_id: str) -> dict[str, Any]:
        """Wait for MCAP ingestion to complete."""
        return dict(self.client.video.wait_for_mcap_ingest(ingest_id, timeout=self.config.timeout_seconds))

    def index(self, video_id: str) -> dict[str, Any]:
        """Run robotics indexing for the primary camera view."""
        results = self.client.index([video_id], mode="robotics", timeout=self.config.timeout_seconds)
        return dict(results[video_id])

    def analysis(self, video_id: str, analysis_id: str) -> dict[str, Any]:
        """Retrieve original events to preserve fractional times and structured fields."""
        return dict(self.client.video.get_video_analysis(video_id, analysis_id))

    def batch(self, batch_id: str) -> dict[str, Any]:
        """Resolve a saved analysis pointer without creating another indexing job."""
        return dict(self.client.get_batch_analysis(batch_id))

    def close(self) -> None:
        """Release the SDK's HTTP connection pool."""
        self.client.session.close()


def primary_video(payload: dict[str, Any]) -> str:
    """Resolve the declared primary view, accepting a sole video for single-view recordings."""
    if payload.get("status") != "completed":
        raise ValueError("Nomadic did not ingest the complete recording.")
    primary = payload.get("primary_view_id") or (payload.get("videos_by_role") or {}).get("front")
    if not primary:
        views = payload.get("views") or {}
        primary = views.get("front") if isinstance(views, dict) else None
    if not primary:
        videos = payload.get("video_ids") or [row["video_id"] for row in payload.get("derived_videos", [])]
        if len(videos) == 1:
            primary = videos[0]
    if not isinstance(primary, str) or not primary:
        raise ValueError("Nomadic did not identify a primary camera view.")
    return primary


def workbench_url(dashboard_url: str, batch_id: str | None, video_id: str) -> str:
    """Build a Workbench link for the saved recording."""
    parsed = urlsplit(dashboard_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("The Nomadic dashboard address must be an HTTPS URL without credentials.")
    target = quote(batch_id, safe="") if batch_id else f"videos/{quote(video_id, safe='')}"
    path = f"{parsed.path.rstrip('/')}/workbench/{target}"
    return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode({"video": video_id}), ""))


def _seconds(value: object) -> float:
    text = str(value).removeprefix("t=")
    total = 0.0
    for component in text.split(":"):
        total = total * 60 + float(component)
    if not math.isfinite(total) or total < 0:
        raise ValueError("Invalid event timestamp.")
    return total


def annotation_events(payload: dict[str, Any], analysis_id: str) -> list[AnnotationEvent]:
    """Normalize action windows while preserving timestamp precision and structured fields."""
    analysis = payload.get("analysis") or payload
    if str(analysis.get("status", "")).lower() not in {"completed", "complete"}:
        raise ValueError("The saved Nomadic analysis is not complete.")
    events = analysis.get("events") or (analysis.get("visual_analysis") or {}).get("events") or []
    if not events:
        # Some indexing responses expose segments under indexing_caption instead of events.
        events = (analysis.get("indexing_caption") or {}).get("segments") or []
    normalized = []
    for event in events:
        data = event.get("data") or {}
        fields = event.get("structured_output") or data.get("structured_output") or event.get("facets") or {}
        start = _seconds(event.get("t_start", event.get("start_time", event.get("time"))))
        end = _seconds(event.get("t_end", event.get("end_time")))
        if end <= start:
            raise ValueError("Nomadic returned an invalid action window.")
        description = str(event.get("description") or event.get("label") or "")
        identity = (
            event.get("event_id")
            or event.get("id")
            or str(uuid5(NAMESPACE_URL, f"{analysis_id}:{start}:{end}:{description}"))
        )
        classes = fields.get("action_classes") or []
        category = classes[0] if classes else event.get("category") or event.get("type")
        hand = fields.get("acting_hand") or event.get("acting_hand")
        normalized.append(
            AnnotationEvent(
                event_id=identity,
                start_seconds=start,
                end_seconds=end,
                description=description,
                category=category,
                acting_hand=hand if hand in {"left", "right", "both"} else None,
                objects=fields.get("objects_interacted_with") or [],
                action_classes=classes,
                gripper_transitions=fields.get("gripper_transitions") or [],
                object_interactions=fields.get("object_interactions") or event.get("object_interactions") or [],
                structured_output=fields,
            )
        )
    return sorted(normalized, key=lambda event: event.start_seconds)
