"""Safe rclpy initialization helper.

Provides a process-wide guard to ensure rclpy.init() is only called once.
This avoids RuntimeError: Context.init() must only be called once when multiple
components attempt to initialize the ROS client library.

API:
- safe_init(args: list[str] | None = None) -> None
- is_initialized() -> bool

Note: We intentionally do not call rclpy.shutdown() globally here because
other parts of the process may still use ROS. Callers that create/destroy
nodes should destroy nodes, but not shutdown rclpy unless they own the
global lifecycle.
"""

from __future__ import annotations

import threading

import rclpy

_guard_lock = threading.Lock()
_initialized = False


def is_initialized() -> bool:
    """Return True if rclpy has already been initialized in this process.

    This checks both the module-level flag and the rclpy runtime state.
    """
    return _initialized or (hasattr(rclpy, "ok") and rclpy.ok())


def safe_init(args: list[str] | None = None) -> None:
    """Initialize rclpy only once per process.

    This is thread-safe and idempotent.
    """
    global _initialized  # noqa: PLW0603
    with _guard_lock:
        if _initialized:
            return
        # rclpy.ok() may also indicate prior initialization; guard against both
        if not (hasattr(rclpy, "ok") and rclpy.ok()):
            if args is None:
                rclpy.init()
            else:
                rclpy.init(args=args)
        _initialized = True


def safe_shutdown() -> None:
    """Shutdown rclpy if the guard marked it as initialized.

    This avoids shutting down a rclpy context that the process does not own.
    """
    global _initialized  # noqa: PLW0603
    with _guard_lock:
        if not _initialized:
            return
        try:
            if hasattr(rclpy, "ok") and rclpy.ok():
                rclpy.shutdown()
        finally:
            _initialized = False
