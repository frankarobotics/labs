"""Nominal FR3 link0-to-flange kinematics; no station or gripper TCP calibration.

Joint origins follow Franka Robotics' franka_description/robots/fr3/kinematics.yaml
at 7aeeddc449edf8d62b594f9e36a81da53e7796f9. Dimensions are metres.
"""

import math

import numpy as np
from numpy.typing import NDArray

_ORIGINS = (
    (0, 0, 0.333, 0),
    (0, 0, 0, -math.pi / 2),
    (0, -0.316, 0, math.pi / 2),
    (0.0825, 0, 0, math.pi / 2),
    (-0.0825, 0.384, 0, -math.pi / 2),
    (0, 0, 0, math.pi / 2),
    (0.088, 0, 0, math.pi / 2),
)


def flange_transform(joints: list[float]) -> NDArray[np.float64]:
    """Return fr3_link8 in fr3_link0 from seven measured joint angles in radians."""
    if len(joints) != 7 or not all(math.isfinite(value) for value in joints):  # noqa: PLR2004
        raise ValueError("FR3 flange kinematics requires seven finite joint angles.")
    transform = np.eye(4)
    for (x, y, z, roll), angle in zip(_ORIGINS, joints, strict=True):
        cr, sr, ca, sa = math.cos(roll), math.sin(roll), math.cos(angle), math.sin(angle)
        transform = transform @ np.array(
            [[ca, -sa, 0, x], [cr * sa, cr * ca, -sr, y], [sr * sa, sr * ca, cr, z], [0, 0, 0, 1]]
        )
    transform[:3, 3] += transform[:3, 2] * 0.107
    return transform


def orientation_xyzw(transform: NDArray[np.float64]) -> list[float]:
    """Return a normalized quaternion, including rotations close to 180 degrees."""
    r = transform[:3, :3]
    k = np.array(
        [
            [r[0, 0] - r[1, 1] - r[2, 2], r[1, 0] + r[0, 1], r[2, 0] + r[0, 2], r[2, 1] - r[1, 2]],
            [r[1, 0] + r[0, 1], r[1, 1] - r[0, 0] - r[2, 2], r[2, 1] + r[1, 2], r[0, 2] - r[2, 0]],
            [r[2, 0] + r[0, 2], r[2, 1] + r[1, 2], r[2, 2] - r[0, 0] - r[1, 1], r[1, 0] - r[0, 1]],
            [r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1], np.trace(r)],
        ]
    )
    quaternion = np.linalg.eigh(k)[1][:, -1]
    if quaternion[3] < 0:
        quaternion = -quaternion
    return [float(value) for value in quaternion]
