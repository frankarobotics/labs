"""Script that reads ROS2 messages from an MCAP bag using the rosbag2_py API."""

import argparse
from collections.abc import Generator
from typing import Any

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message  # type: ignore


def read_messages(input_bag: str) -> Generator[tuple[str, Any, int], None, None]:
    """Read messages from an MCAP bag file."""
    reader: rosbag2_py.SequentialReader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=input_bag, storage_id="mcap"),
        rosbag2_py.ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr"),
    )

    topic_types: list[rosbag2_py.TopicMetadata] = reader.get_all_topics_and_types()  # type: ignore

    def typename(topic_name: str) -> Any:  # noqa: ANN401
        for topic_type in topic_types:
            if topic_type.name == topic_name:
                return topic_type.type
        raise ValueError(f"topic {topic_name} not in bag")

    while reader.has_next():
        topic: str
        data: bytes
        timestamp: int
        topic, data, timestamp = reader.read_next()
        msg_type = get_message(typename(topic))
        msg: Any = deserialize_message(data, msg_type)
        yield topic, msg, timestamp
    del reader


def print_statistics(  # noqa: PLR0913
    message_count: int,
    topic_counts: dict[str, int],
    topic_type_counts: dict[str, dict[str, int]],
    min_timestamp: int | None,
    max_timestamp: int | None,
    topic_timestamps: dict[str, tuple[int | None, int | None]],
) -> None:
    """Print statistics for the bag messages."""
    print("\n--- Statistics ---")
    print(f"Total messages: {message_count}")
    print("Messages per topic:")
    for topic, count in topic_counts.items():
        print(f"  {topic}: {count}")
        print("    Message types:")
        for msg_type, type_count in topic_type_counts[topic].items():
            print(f"      {msg_type}: {type_count}")
        topic_min, topic_max = topic_timestamps[topic]
        if topic_min is not None and topic_max is not None:
            print(f"    Timestamp range: {topic_min} - {topic_max} (duration: {topic_max - topic_min} ns)")
        else:
            print("    No messages for this topic.")
    if min_timestamp is not None and max_timestamp is not None:
        print(f"Timestamp range: {min_timestamp} - {max_timestamp} (duration: {max_timestamp - min_timestamp} ns)")
    else:
        print("No messages found.")


def process_bag(input_path: str) -> None:
    """Process the bag file and print messages and statistics."""
    message_count: int = 0
    topic_counts: dict[str, int] = {}
    topic_type_counts: dict[str, dict[str, int]] = {}
    min_timestamp: int | None = None
    max_timestamp: int | None = None
    topic_timestamps: dict[str, tuple[int | None, int | None]] = {}
    for topic, msg, timestamp in read_messages(input_path):
        # Print only the first few items of the message to avoid long image data
        max_msg_length: int = 300
        msg_str: str = str(msg)
        if len(msg_str) > max_msg_length:
            msg_str = msg_str[:max_msg_length] + "..."
        print(f"{topic} ({type(msg).__name__}) [{timestamp}]: '{msg_str}'")
        message_count += 1
        if topic not in topic_counts:
            topic_counts[topic] = 0
            topic_type_counts[topic] = {}
            topic_timestamps[topic] = (None, None)
        topic_counts[topic] += 1
        msg_type_name: str = type(msg).__name__
        if msg_type_name not in topic_type_counts[topic]:
            topic_type_counts[topic][msg_type_name] = 0
        topic_type_counts[topic][msg_type_name] += 1
        # Update global min/max
        if min_timestamp is None or timestamp < min_timestamp:
            min_timestamp = timestamp
        if max_timestamp is None or timestamp > max_timestamp:
            max_timestamp = timestamp
        # Update per-topic min/max
        topic_min, topic_max = topic_timestamps[topic]
        if topic_min is None or timestamp < topic_min:
            topic_min = timestamp
        if topic_max is None or timestamp > topic_max:
            topic_max = timestamp
        topic_timestamps[topic] = (topic_min, topic_max)

    print_statistics(
        message_count=message_count,
        topic_counts=topic_counts,
        topic_type_counts=topic_type_counts,
        min_timestamp=min_timestamp,
        max_timestamp=max_timestamp,
        topic_timestamps=topic_timestamps,
    )


def main() -> None:
    """Main function to parse arguments and process the bag."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="input bag path (folder or filepath) to read from")
    args: argparse.Namespace = parser.parse_args()
    process_bag(args.input)


if __name__ == "__main__":
    main()
