"""Target-rate timestamp grid shared by video decoding and synchronization."""

import numpy as np
import numpy.typing as npt

NS_PER_S = 1_000_000_000


def grid_intervals(duration_ns: int, fps: int) -> int:
    """Whole 1/fps intervals a span covers."""
    # integer arithmetic: float flooring undercounts exact spans, e.g. 1e9 // (1e9 / 7) == 6.0
    return int(duration_ns) * fps // NS_PER_S


def grid_timestamps_ns(start_ns: int, count: int, fps: int) -> npt.NDArray[np.int64]:
    """Timestamps of the first ``count`` grid points from ``start_ns``."""
    # exact 1/fps steps, since LeRobot stamps frame i at i / fps; spreading to an end time would stretch time
    return start_ns + np.round(np.arange(count) * (NS_PER_S / fps)).astype(np.int64)
