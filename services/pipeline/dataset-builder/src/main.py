#!/usr/bin/env python3
"""CLI entry point for dataset building from MCAP files."""

import argparse
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from services.dataset_builder import (
    SingleDatasetBuildRequest,
    UnsupportedDatasetFormatError,
    build_single_dataset,
    list_supported_formats,
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


def validate_single_request(request: SingleDatasetBuildRequest) -> None:
    """Validate a single-file build request."""
    if not request.input_path.exists():
        raise FileNotFoundError(f"Input MCAP file not found: {request.input_path}")

    if request.input_path.suffix != ".mcap":
        raise ValueError(f"Input file must be a .mcap file: {request.input_path}")

    request.output_dir.mkdir(parents=True, exist_ok=True)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    supported_formats = list_supported_formats()
    parser = argparse.ArgumentParser(
        description="Build dataset artifacts from MCAP files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
          Examples:
            # Convert a single MCAP file to LeRobot
            python src/main.py --dataset-name my_robot_data single --input episode.mcap

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
    parser.add_argument("--fps", type=float, default=20.0, help="Target frame rate for synchronization (default: 20.0)")
    parser.add_argument(
        "--dataset-name",
        required=True,
        help="Dataset name — also determines the output path unless --output is set explicitly",
    )
    parser.add_argument(
        "--deployment-dir",
        type=Path,
        help="Path to a deployment directory (e.g. deployments/example_station). "
        "Automatically resolves config_station.yml, config_data_recorder.yml, and modality.json from that folder "
        "unless --station-config / --recorder-config / --modality-config are given explicitly.",
    )
    parser.add_argument(
        "--station-config",
        type=Path,
        help="Path to config_station.yml used to classify observation and action topics",
    )
    parser.add_argument(
        "--recorder-config",
        type=Path,
        help="Path to config_data_recorder.yml used to validate recorded topics",
    )
    parser.add_argument(
        "--modality-config",
        type=Path,
        help="Path to modality.json defining observation.state structure and annotation features",
    )

    subparsers = parser.add_subparsers(dest="command", help="Build mode")
    single_parser = subparsers.add_parser("single", help="Build a dataset from a single MCAP file")
    single_parser.add_argument("--input", "-i", type=Path, required=True, help="Input MCAP file")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Derive output directory from dataset name when not provided
    if args.output is None:
        args.output = Path("/workspace/data/datasets/lerobot") / args.dataset_name

    # Resolve config paths from --deployment-dir when not provided explicitly
    if args.deployment_dir is not None:
        if args.station_config is None:
            candidate = args.deployment_dir / "config_station.yml"
            if candidate.exists():
                args.station_config = candidate
        if args.recorder_config is None:
            candidate = args.deployment_dir / "config_data_recorder.yml"
            if candidate.exists():
                args.recorder_config = candidate
        if args.modality_config is None:
            candidate = args.deployment_dir / "modality.json"
            if candidate.exists():
                args.modality_config = candidate

    return args


def run_single_build(args: argparse.Namespace) -> None:
    """Run a single-file dataset build."""
    request = SingleDatasetBuildRequest(
        input_path=args.input,
        output_dir=args.output,
        target_format=args.format,
        target_fps=args.fps,
        dataset_name=args.dataset_name,
        station_config_path=args.station_config,
        recorder_config_path=args.recorder_config,
        modality_config_path=args.modality_config,
    )
    validate_single_request(request)

    logger.info(f"Building dataset from MCAP file: {request.input_path}")
    logger.info(f"Target format: {request.target_format}")

    result: dict[str, Any] = build_single_dataset(request)
    logger.info("Dataset build completed successfully")
    logger.info(f"Dataset directory: {result['dataset_dir']}")
    logger.info(f"Episode metadata: {result['episode_metadata']}")
    logger.info("Generated metadata files:")
    for file_type, file_path in result["metadata_files"].items():
        logger.info(f"  {file_type}: {file_path}")


def main() -> None:
    """Main CLI entry point."""
    args = parse_args()
    setup_logging(args.verbose)

    try:
        if args.command == "single":
            run_single_build(args)
    except (FileNotFoundError, ValueError, UnsupportedDatasetFormatError) as exc:
        logger.error(str(exc))
        sys.exit(1)
    except Exception as exc:
        logger.error(f"Dataset build failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
