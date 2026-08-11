#!/usr/bin/env python3
"""CLI entry point for dataset building from MCAP files."""

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

from loguru import logger
from pipeline_configs import POLICY_CONTRACT_FILE

from services.dataset_builder import (
    DatasetBuildRequest,
    UnsupportedDatasetFormatError,
    build_dataset,
    list_supported_formats,
)
from services.episode_discovery import (
    DEFAULT_EPISODES_DIR,
    DiscoveredEpisode,
    EpisodeFilter,
    discover_episodes,
)


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level=level,
    )


def _date_type(value: str) -> date:
    """Parse a YYYY-MM-DD string into a :class:`datetime.date`."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date '{value}' (expected YYYY-MM-DD)") from exc


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    supported_formats = list_supported_formats()
    parser = argparse.ArgumentParser(
        description="Build dataset artifacts from processed MCAP episodes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
          Examples:
            # All processed episodes
            python src/main.py --dataset-name my_data

            # Filter by date range
            python src/main.py --dataset-name may_data --from 2026-05-01 --to 2026-05-31

            # Filter by task description
            python src/main.py --dataset-name pick_data --task "Pick red box"

            # Explicit MCAP file(s)
            python src/main.py --dataset-name single_ep --input episode.mcap

          Supported formats: {", ".join(supported_formats)}
        """,
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--format",
        default="lerobot",
        choices=supported_formats,
        help="Target dataset format (default: lerobot)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output directory for the built dataset (default: /workspace/data/datasets/lerobot/<dataset-name>)",
    )
    parser.add_argument(
        "--fps",
        type=float,
        help="Override the output FPS (recommended default: contract's policy.control_rate_hz)",
    )
    parser.add_argument(
        "--dataset-name",
        required=True,
        help="Dataset name — also determines the output path unless --output is set explicitly",
    )
    parser.add_argument(
        "--deployment-dir",
        type=Path,
        help="Path to a deployment directory (e.g. deployments/fr3_duo_example)",
    )
    parser.add_argument(
        "--policy-type",
        default="gr00t",
        help="Policy model the contract targets; selects config_contract_<policy-type>.yml "
        "when --policy-contract is not set explicitly (default: gr00t)",
    )
    parser.add_argument(
        "--policy-contract",
        type=Path,
        help="Path to the policy contract YAML file, which declares the cameras, state and action segments to "
        f"extract (default: <deployment-dir>/config_contract_<policy-type>.yml, else {POLICY_CONTRACT_FILE})",
    )

    input_group = parser.add_argument_group("explicit input (mutually exclusive with discovery filters)")
    input_group.add_argument(
        "--input",
        "-i",
        type=Path,
        action="append",
        dest="inputs",
        help="Path to an MCAP file (repeatable). When given, discovery filters are ignored.",
    )

    filter_group = parser.add_argument_group("discovery filters (mutually exclusive with --input)")
    filter_group.add_argument(
        "--episodes-dir",
        type=Path,
        default=DEFAULT_EPISODES_DIR,
        help=f"Root directory of processed episodes (default: {DEFAULT_EPISODES_DIR})",
    )
    filter_group.add_argument(
        "--from",
        dest="from_date",
        type=_date_type,
        metavar="YYYY-MM-DD",
        help="Include episodes recorded on or after this date (inclusive)",
    )
    filter_group.add_argument(
        "--to",
        dest="to_date",
        type=_date_type,
        metavar="YYYY-MM-DD",
        help="Include episodes recorded on or before this date (inclusive)",
    )
    filter_group.add_argument(
        "--task",
        action="append",
        dest="tasks",
        help="Filter by task description (case-insensitive substring, repeatable)",
    )
    filter_group.add_argument(
        "--episode-id",
        type=UUID,
        action="append",
        dest="episode_ids",
        help="Include a specific episode UUID (repeatable)",
    )
    filter_group.add_argument(
        "--exclude-id",
        type=UUID,
        action="append",
        dest="exclude_ids",
        help="Exclude a specific episode UUID (repeatable)",
    )
    filter_group.add_argument("--limit", type=int, help="Maximum number of episodes to include")
    filter_group.add_argument(
        "--include-failed",
        action="store_true",
        help="Include episodes marked as failed (excluded by default)",
    )
    filter_group.add_argument(
        "--dry-run",
        action="store_true",
        help="List matched episodes and exit without converting",
    )

    args = parser.parse_args()

    # Mutual exclusivity: --input vs discovery filters
    has_inputs = bool(args.inputs)
    has_filters = any([args.from_date, args.to_date, args.tasks, args.episode_ids, args.exclude_ids, args.limit])
    if has_inputs and has_filters:
        parser.error(
            "--input and discovery filters (--from, --to, --task, --episode-id, --exclude-id, --limit) "
            "are mutually exclusive"
        )
    if has_inputs and args.dry_run:
        parser.error("--dry-run only applies to discovery filters and cannot be combined with --input")

    # Derive output directory from dataset name when not provided
    if args.output is None:
        args.output = Path("/workspace/data/datasets/lerobot") / args.dataset_name

    if args.policy_contract is None:
        args.policy_contract = (
            args.deployment_dir / f"config_contract_{args.policy_type}.yml"
            if args.deployment_dir is not None
            else POLICY_CONTRACT_FILE
        )

    return args


def _resolve_explicit_inputs(inputs: list[Path]) -> tuple[Path, ...]:
    """Validate and return explicit ``--input`` MCAP paths."""
    for p in inputs:
        if not p.exists():
            raise FileNotFoundError(f"Input MCAP file not found: {p}")
        if p.suffix != ".mcap":
            raise ValueError(f"Input file must be a .mcap file: {p}")
    return tuple(inputs)


def _discover_episodes(args: argparse.Namespace) -> list[DiscoveredEpisode]:
    """Build an :class:`EpisodeFilter` from CLI args and run discovery."""
    episode_filter = EpisodeFilter(
        from_date=args.from_date,
        to_date=args.to_date,
        task_names=tuple(args.tasks) if args.tasks else (),
        episode_ids=tuple(args.episode_ids) if args.episode_ids else (),
        exclude_ids=tuple(args.exclude_ids) if args.exclude_ids else (),
        limit=args.limit,
        include_failed=args.include_failed,
    )
    return discover_episodes(args.episodes_dir, episode_filter)


def _log_dry_run(episodes: list[DiscoveredEpisode]) -> None:
    """Log the episodes matched by discovery without converting them."""
    logger.info(f"Dry run: {len(episodes)} episode(s) matched")
    for ep in episodes:
        task = ep.task_description or "(unknown)"
        logger.info(f"  {ep.recorded_date}  {ep.episode_id}  task={task}  {ep.mcap_path}")


def run_build(args: argparse.Namespace) -> None:
    """Resolve inputs and build the dataset."""
    if args.inputs:
        mcap_files = _resolve_explicit_inputs(args.inputs)
    else:
        episodes = _discover_episodes(args)
        if args.dry_run:
            _log_dry_run(episodes)
            return
        if not episodes:
            raise ValueError(
                f"No episodes found in {args.episodes_dir} matching the given filters. "
                "Use --dry-run to debug, or provide explicit --input paths."
            )
        mcap_files = tuple(ep.mcap_path for ep in episodes)

    logger.info(f"Building dataset '{args.dataset_name}' from {len(mcap_files)} episode(s)")

    request = DatasetBuildRequest(
        mcap_files=mcap_files,
        output_dir=args.output,
        target_format=args.format,
        dataset_name=args.dataset_name,
        policy_contract_path=args.policy_contract,
        policy_type=args.policy_type,
        target_fps=args.fps,
    )

    if request.output_dir.exists() and any(request.output_dir.iterdir()):
        raise ValueError(
            f"Output directory is not empty: {request.output_dir}. "
            "Remove it or choose a different --output/--dataset-name to avoid mixing with stale files."
        )
    request.output_dir.mkdir(parents=True, exist_ok=True)

    try:
        result: dict[str, Any] = build_dataset(request)
    except Exception:
        try:
            shutil.rmtree(request.output_dir)
            logger.info(f"Removed partial dataset at {request.output_dir} due to failure during dataset creation")
        except OSError as cleanup_error:
            logger.error(f"Failed to remove partial dataset at {request.output_dir}: {cleanup_error}")
        raise

    episode_metadata = result["episode_metadata"]
    metadata_files = result["metadata_files"]

    logger.info("Dataset build completed successfully")
    logger.info(f"Dataset directory: {result['dataset_dir']}")
    logger.info(f"Episodes converted: {len(episode_metadata)}")
    logger.info("Generated metadata files:")
    for file_type, file_path in metadata_files.items():
        logger.info(f"  {file_type}: {file_path}")


def main() -> None:
    """Main CLI entry point."""
    args = parse_args()
    setup_logging(args.verbose)

    try:
        run_build(args)
    except (FileNotFoundError, ValueError, UnsupportedDatasetFormatError) as exc:
        logger.error(str(exc))
        sys.exit(1)
    except Exception as exc:
        logger.error(f"Dataset build failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
