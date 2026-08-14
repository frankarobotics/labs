"""Episode discovery and filtering for processed MCAP episodes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import UUID

import mcap.reader  # type: ignore[import-untyped]
from loguru import logger

DEFAULT_EPISODES_DIR = Path("/workspace/data/processed_episodes")


@dataclass(frozen=True)
class EpisodeFilter:
    """Criteria for selecting processed episodes.

    All active filters are combined with AND logic.
    """

    from_date: date | None = None
    to_date: date | None = None
    task_names: tuple[str, ...] = ()
    episode_ids: tuple[UUID, ...] = ()
    exclude_ids: tuple[UUID, ...] = ()
    limit: int | None = None
    include_failed: bool = False


@dataclass
class DiscoveredEpisode:
    """An episode found on disk with extracted metadata."""

    mcap_path: Path
    episode_id: UUID
    recorded_date: date
    task_description: str | None = None


def discover_episodes(
    episodes_dir: Path = DEFAULT_EPISODES_DIR,
    episode_filter: EpisodeFilter | None = None,
) -> list[DiscoveredEpisode]:
    """Scan *episodes_dir* for processed MCAP episodes and apply *episode_filter*.

    Directory layout expected::

        episodes_dir/YYYY/MM/DD/<uuid>/mcap/mcap_0.mcap

    Returns a deterministically sorted list (by date then UUID).
    """
    if not episodes_dir.is_dir():
        raise FileNotFoundError(f"Episodes directory does not exist: {episodes_dir}")

    ef = episode_filter or EpisodeFilter()
    candidates = _scan_directory(episodes_dir)
    filtered = _apply_path_filters(candidates, ef)

    if ef.task_names:
        filtered = _apply_task_filter(filtered, ef.task_names)

    # Deterministic sort: date ascending, then UUID string
    filtered.sort(key=lambda e: (e.recorded_date, str(e.episode_id)))

    if ef.limit is not None:
        filtered = filtered[: ef.limit]

    # Populate task_description for episodes not already enriched by task filtering
    for ep in filtered:
        if ep.task_description is None:
            ep.task_description = _read_task_description(ep.mcap_path)

    return filtered


def _scan_directory(episodes_dir: Path) -> list[DiscoveredEpisode]:
    """Walk the YYYY/MM/DD/<uuid>/mcap/mcap_0.mcap tree."""
    episodes: list[DiscoveredEpisode] = []

    for mcap_path in sorted(episodes_dir.glob("*/*/*/*/mcap/mcap_0.mcap")):
        # Expected: .../YYYY/MM/DD/<uuid>/mcap/mcap_0.mcap
        try:
            episode_dir = mcap_path.parent.parent  # up from mcap/
            uuid_str = episode_dir.name
            day = int(episode_dir.parent.name)
            month = int(episode_dir.parent.parent.name)
            year = int(episode_dir.parent.parent.parent.name)
            recorded = date(year, month, day)
            episode_id = UUID(uuid_str)
        except (ValueError, IndexError):
            logger.warning(f"Skipping path with unexpected structure: {mcap_path}")
            continue

        episodes.append(
            DiscoveredEpisode(
                mcap_path=mcap_path,
                episode_id=episode_id,
                recorded_date=recorded,
            )
        )

    logger.info(f"Scanned {episodes_dir}: found {len(episodes)} episode(s)")
    return episodes


def _read_episode_label(episode_dir: Path) -> str | None:
    """Read the ``label`` field from *episode_dir*/episode_metadata.json, or None."""
    metadata_path = episode_dir / "episode_metadata.json"
    if not metadata_path.exists():
        return None
    try:
        return json.loads(metadata_path.read_text()).get("label")
    except Exception:
        logger.warning(f"Could not read episode_metadata.json in {episode_dir}")
        return None


def _apply_path_filters(
    episodes: list[DiscoveredEpisode],
    ef: EpisodeFilter,
) -> list[DiscoveredEpisode]:
    """Apply cheap, path-only filters (date range, episode IDs, exclusions)."""
    result: list[DiscoveredEpisode] = []

    id_allowlist = set(ef.episode_ids) if ef.episode_ids else None
    id_blocklist = set(ef.exclude_ids) if ef.exclude_ids else set()

    for ep in episodes:
        label = _read_episode_label(ep.mcap_path.parent.parent)
        if label != "REVIEW_SUCCESS" and not (ef.include_failed and label == "REVIEW_FAILED"):
            continue
        if ef.from_date and ep.recorded_date < ef.from_date:
            continue
        if ef.to_date and ep.recorded_date > ef.to_date:
            continue
        if id_allowlist is not None and ep.episode_id not in id_allowlist:
            continue
        if ep.episode_id in id_blocklist:
            continue
        result.append(ep)

    dropped = len(episodes) - len(result)
    if dropped:
        logger.info(f"Path and date filters excluded {dropped} episode(s), {len(result)} remaining")

    return result


def _apply_task_filter(
    episodes: list[DiscoveredEpisode],
    task_names: tuple[str, ...],
) -> list[DiscoveredEpisode]:
    """Read MCAP metadata to filter by task description (case-insensitive substring)."""
    needles = [t.lower() for t in task_names]
    result: list[DiscoveredEpisode] = []

    for ep in episodes:
        task_desc = _read_task_description(ep.mcap_path)
        ep.task_description = task_desc

        if task_desc is None:
            logger.debug(f"No task description in {ep.mcap_path}, excluding from task filter")
            continue

        if any(n in task_desc.lower() for n in needles):
            result.append(ep)

    dropped = len(episodes) - len(result)
    if dropped:
        logger.info(f"Task filter excluded {dropped} episode(s), {len(result)} remaining")

    return result


def _read_task_description(mcap_path: Path) -> str | None:
    """Read only the MCAP metadata section to extract the task description.

    This is fast — it reads metadata records, not messages.
    """
    try:
        with open(mcap_path, "rb") as f:
            reader = mcap.reader.make_reader(f)
            for meta in reader.iter_metadata():
                if meta.name == "episode_context":
                    serialized = meta.metadata.get("data")
                    if serialized:
                        decoded = json.loads(serialized)
                        return decoded.get("task_description")
    except Exception as exc:
        logger.warning(f"Failed to read metadata from {mcap_path}: {exc}")

    return None
