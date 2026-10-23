"""Read the reference station's recorded arm-base transforms without inventing placement."""

from pathlib import Path
from typing import Any

import numpy as np
from mcap.reader import make_reader
from mcap_ros2.decoder import DecoderFactory
from numpy.typing import NDArray


def _matrix(transform: Any) -> NDArray[np.float64]:  # noqa: ANN401 -- Decoded ROS Transform.
    translation, rotation = transform.translation, transform.rotation
    values = [translation.x, translation.y, translation.z, rotation.x, rotation.y, rotation.z, rotation.w]
    if not all(np.isfinite(values)):
        raise ValueError("Recorded arm-base transforms must contain finite values.")
    quaternion = np.array(values[3:], dtype=float)
    norm = float(np.linalg.norm(quaternion))
    if abs(norm - 1) > 1e-3:  # noqa: PLR2004
        raise ValueError("Recorded arm-base transforms must contain unit quaternions.")
    x, y, z, w = quaternion / norm
    matrix = np.eye(4)
    matrix[:3, :3] = [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]
    matrix[:3, 3] = values[:3]
    return matrix


def recorded_arm_bases(source: Path) -> tuple[str, dict[str, NDArray[np.float64]]]:
    """Require consistent static transforms from one parent to both reference arm bases."""
    frames = {f"{side}_fr3_link0": side for side in ("left", "right")}
    found: dict[str, tuple[str, NDArray[np.float64]]] = {}
    factory = DecoderFactory()
    with source.open("rb") as handle:
        for schema, channel, message in make_reader(handle).iter_messages(topics=["/tf_static"]):
            if schema is None or schema.name != "tf2_msgs/msg/TFMessage" or channel.message_encoding != "cdr":
                raise ValueError("The reference arm-base mapping requires ROS 2 /tf_static transforms.")
            decode = factory.decoder_for(channel.message_encoding, schema)
            if decode is None:
                raise ValueError("Recorded arm-base transforms cannot be decoded.")
            for transform in decode(message.data).transforms:
                child = transform.child_frame_id.lstrip("/")
                if child not in frames:
                    continue
                parent = transform.header.frame_id.lstrip("/")
                if not parent or parent in frames:
                    raise ValueError("Reference arm bases must share an explicit parent frame.")
                matrix = _matrix(transform.transform)
                previous = found.get(child)
                if previous and (previous[0] != parent or not np.allclose(previous[1], matrix, rtol=0, atol=1e-9)):
                    raise ValueError(f"Conflicting recorded static transform for {child}.")
                found[child] = (parent, matrix)
    if set(found) != set(frames):
        raise ValueError("The reference mapping requires recorded /tf_static transforms for both FR3 arm bases.")
    parents = {parent for parent, _ in found.values()}
    if len(parents) != 1:
        raise ValueError("Recorded FR3 arm bases have different parents; a custom frame mapping is required.")
    return parents.pop(), {frames[child]: matrix for child, (_, matrix) in found.items()}
