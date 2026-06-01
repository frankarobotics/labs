import argparse
import math
import os
from collections.abc import Iterator
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import rosbag2_py  # pyright: ignore[reportMissingImports]
import seaborn as sns
from loguru import logger
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message  # type: ignore


class MCAPReader:
    """Read and analyze MCAP files."""

    def get_all_topics_stats(self) -> dict[str, dict[str, Any]]:
        """Return statistics for all topics in the MCAP file."""
        stats = {}
        for topic in self.get_topics():
            stats[topic] = self.get_topic_stats(topic)
        return stats

    def __init__(self, mcap_path: str) -> None:
        """Initialize the MCAP reader with the path to the MCAP file.

        Args:
            mcap_path (str): Path to the MCAP file.
        """
        self.mcap_path: str = mcap_path

    def read(self, filter_topics: list[str] | None = None) -> Iterator[tuple[str, Any, int]]:
        """Yield (topic, msg, timestamp) from the MCAP file, optionally filtering topics."""
        reader = rosbag2_py.SequentialReader()
        reader.open(
            rosbag2_py.StorageOptions(uri=self.mcap_path, storage_id="mcap"),
            rosbag2_py.ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr"),
        )
        topic_types = reader.get_all_topics_and_types()  # type: ignore[no-untyped-call]
        type_map = {t.name: t.type for t in topic_types}

        def typename(topic_name: str) -> str:
            if topic_name in type_map:
                return str(type_map[topic_name])
            raise ValueError(f"topic {topic_name} not in bag")

        while reader.has_next():
            topic, data, timestamp = reader.read_next()
            if filter_topics is not None and topic not in filter_topics:
                continue
            msg_type = get_message(typename(topic))
            msg = deserialize_message(data, msg_type)
            yield topic, msg, timestamp
        del reader

    def get_topics(self) -> list[str]:
        """Return a list of topic names in the MCAP file."""
        reader = rosbag2_py.SequentialReader()
        reader.open(
            rosbag2_py.StorageOptions(uri=self.mcap_path, storage_id="mcap"),
            rosbag2_py.ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr"),
        )
        topic_types = reader.get_all_topics_and_types()  # type: ignore[no-untyped-call]
        topics = [t.name for t in topic_types]
        del reader
        return topics

    def get_stats(self) -> dict[str, Any]:
        """Return global statistics for the MCAP file: total messages, topics, time span, etc."""
        total_count = 0
        first_ts: int | None = None
        last_ts: int | None = None
        topics: list[str] = self.get_topics()
        topic_counts: dict[str, int] = dict.fromkeys(topics, 0)
        for topic, _, ts in self.read():
            if total_count == 0:
                first_ts = ts
            last_ts = ts
            total_count += 1
            topic_counts[topic] += 1
        duration: float = (
            (last_ts - first_ts) / 1e9 if total_count > 1 and first_ts is not None and last_ts is not None else 0.0
        )
        avg_freq: float | None = total_count / duration if duration > 0 else None
        return {
            "total_messages": total_count,
            "num_topics": len(topics),
            "topics": topics,
            "first_timestamp": first_ts,
            "last_timestamp": last_ts,
            "duration": duration,
            "average_frequency": avg_freq,
            "messages_per_topic": topic_counts,
        }

    def get_topic_stats(self, topic: str) -> dict[str, int | float | str | None | list[float]]:
        """Return statistics for a given topic."""
        timestamps: list[int] = []
        for _t, _, ts in self.read([topic]):
            timestamps.append(ts)
        count: int = len(timestamps)
        if count == 0:
            return {
                "topic": topic,
                "count": 0,
                "first_timestamp": None,
                "last_timestamp": None,
                "duration": None,
                "frequency": None,
                "min_period": None,
                "max_period": None,
                "mean_period": None,
                "std_period": None,
                "expected_count": None,
                "drop_count": None,
                "drop_fraction": None,
            }
        first_ts: int = timestamps[0]
        last_ts: int = timestamps[-1]
        duration: float = (last_ts - first_ts) / 1e9 if count > 1 else 0.0
        freq: float | None = count / duration if duration > 0 else None
        periods: list[float] = [(timestamps[i] - timestamps[i - 1]) / 1e9 for i in range(1, count)]
        min_period: float | None = None
        max_period: float | None = None
        mean_period: float | None = None
        std_period: float | None = None
        expected_count: float | None = None
        drop_count: int | None = None
        drop_fraction: float | None = None
        if periods:
            min_period = min(periods)
            max_period = max(periods)
            mean_period = sum(periods) / len(periods)
            std_period = (
                math.sqrt(sum((p - mean_period) ** 2 for p in periods) / len(periods)) if len(periods) > 1 else 0.0
            )
            # Frequency drop analysis
            if mean_period and duration > 0:
                expected_count = duration / mean_period + 1
                threshold: float = 2 * mean_period
                drop_count = len([p for p in periods if p > threshold])
                drop_fraction = drop_count / len(periods) if periods else 0.0
        return {
            "topic": topic,
            "count": count,
            "first_timestamp": first_ts,
            "last_timestamp": last_ts,
            "duration": duration,
            "frequency": freq,
            "min_period": min_period,
            "max_period": max_period,
            "mean_period": mean_period,
            "std_period": std_period,
            "expected_count": expected_count,
            "drop_count": drop_count,
            "drop_fraction": drop_fraction,
        }

    def plot_frequency_over_time_all(self, window_sec: float = 1.0) -> None:
        """Plot frequency over time for all topics using seaborn.

        Each topic saves to 'output/frequency_<topic>_frequency.png'.
        """
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        for topic in self.get_topics():
            timestamps: list[float] = [ts / 1e9 for _t, _, ts in self.read([topic])]
            if not timestamps:
                print(f"No messages found for topic: {topic}")
                continue
            timestamps.sort()
            start: float = timestamps[0]
            end: float = timestamps[-1]
            bins = np.arange(start, end + window_sec, window_sec)
            counts, _ = np.histogram(timestamps, bins)
            freqs = counts / window_sec
            bin_centers = bins[:-1] + window_sec / 2
            sns.set_theme(style="whitegrid")
            plt.figure(figsize=(10, 5))
            sns.lineplot(x=bin_centers, y=freqs, marker="o", label=f"Frequency ({window_sec}s window)")
            plt.xlabel("Time (s)")
            plt.ylabel("Frequency (Hz)")
            plt.title(f"Frequency over time for topic: {topic}")
            plt.legend()
            filename: str = f"{topic.replace('/', '_')}_frequency.png"
            if filename.startswith("_"):
                filename = filename[1:]
            output_path: str = os.path.join(output_dir, filename)
            plt.savefig(output_path)
            print(f"Plot saved to {output_path}")
            plt.close()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the MCAP reader CLI.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(description="MCAP Reader")
    parser.add_argument(
        "-f", "--file", dest="mcap", required=True, metavar="PATH", help="Path to the MCAP file to analyze."
    )
    parser.add_argument(
        "-s",
        "--stats",
        action="store_true",
        help="Print global statistics and per-topic statistics about the MCAP file.",
    )
    parser.add_argument(
        "-p",
        "--plot-frequency",
        action="store_true",
        help="Plot frequency over time for all topics. Each topic will generate one image.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args: argparse.Namespace = parse_args()
    reader = MCAPReader(args.mcap)
    if args.plot_frequency:
        # Plot frequency over time for all topics
        reader.plot_frequency_over_time_all()
    elif args.stats:
        stats = reader.get_stats()
        print("Global MCAP file stats:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        all_stats = reader.get_all_topics_stats()
        print("\nStats for all topics:")
        for topic, topic_stats in all_stats.items():
            print(f"Topic: {topic}")
            for k, v in topic_stats.items():
                print(f"  {k}: {v}")
            print()
    else:
        logger.info(f"Reading MCAP: {args.mcap}")
        for topic, msg, timestamp in reader.read():
            logger.info(f"{topic} [{timestamp}]: {msg}")
