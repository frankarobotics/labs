"""Handler for intercepting standard logging and redirecting to loguru."""

import logging
import sys
from types import FrameType
from typing import Any

from loguru import logger

from configs.logger import LoggerConfig, load_logger_config


def loguru_format(record: dict[str, Any], path_prefix: str) -> str:
    """Format loguru record to show absolute file path and line number.

    Args:
        record: Loguru record object.
        path_prefix: Path prefix to use for formatting.

    Returns:
        str: Formatted log string with absolute file path and line number.
    """
    path: str = record["file"].path
    # Enable clicking of file paths in the log output to open in editor
    if path_prefix and path.startswith("/workspace/"):
        path = path.replace("/workspace/", path_prefix)
    thread_id = record["thread"].id

    # Protect against sinks that perform format-style interpolation on the entire format string: if the log message
    # itself contains braces (for example when logging dicts like "{'limit': 10}"), Python's str.format used by some
    # formatters may attempt to interpret those braces as placeholders and raise a KeyError. Escape braces in the
    # message so they're treated literally in any downstream formatting.
    msg_text: str = str(record.get("message", ""))
    if "{" in msg_text or "}" in msg_text:
        msg_text = msg_text.replace("{", "{{").replace("}", "}}")
    # Escape angle brackets so that literal text like '<function ...>' or '<locals>' is not interpreted as a Loguru
    # color directive. Prefixing with a backslash makes Colorizer treat them as literal characters.
    if "<" in msg_text or ">" in msg_text:
        msg_text = msg_text.replace("<", "\\<").replace(">", "\\>")

    return (
        f"<green>{record['time']:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        f"<magenta>{thread_id}</magenta> | "
        f"<level>{record['level']:8}</level> | "
        f"<cyan>{path}:{record['line']}</cyan> | "
        f"{msg_text}\n"
    )


class InterceptHandler(logging.Handler):
    """Intercept all logging records and redirect them to loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        """Pass every log record to loguru.

        Args:
            record: The log record to emit.
        """
        # Get corresponding Loguru level if it exists
        try:
            level: str = logger.level(record.levelname).name
        except ValueError:
            level = str(record.levelno)  # Convert int to str for level

        # Find caller from where the logged message originated
        current_frame: FrameType = logging.currentframe()
        depth = 2

        # Only process frame if it exists
        if current_frame is not None:
            frame: FrameType = current_frame
            while frame.f_code.co_filename == logging.__file__:
                next_frame: FrameType | None = frame.f_back
                if next_frame is None:
                    break
                frame = next_frame
                depth += 1

        # Protect against Loguru's formatting when the message contains braces like '{' or '}'. Loguru uses
        # str.format-style placeholders in its sink formatting and will raise a KeyError if the message contains
        # unmatched braces. To avoid this, escape braces in the message before passing it to loguru.
        msg: str = record.getMessage()
        if "{" in msg or "}" in msg:
            # Escape single braces so they are treated as literal characters by Loguru's formatting machinery.
            msg = msg.replace("{", "{{").replace("}", "}}")

        logger.opt(depth=depth, exception=record.exc_info).log(level, msg)


def setup_logging(config: LoggerConfig | None = None) -> None:
    """Configure logging with loguru.

    Args:
        config: Logger configuration. If not provided, it will be loaded.
    """
    # Load config if not provided
    if config is None:
        config = load_logger_config()

    # Remove default handlers
    logger.remove()

    # Add console handler
    logger.add(
        sys.stderr,
        level=config.log_level,
        format=lambda record: loguru_format(record, config.path_prefix),  # pyright: ignore[reportArgumentType]
        colorize=True,
    )

    # Intercept standard logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Suppress very verbose debug logs from AWS/boto3 libraries.
    libs = ("boto3", "botocore", "s3transfer", "urllib3")
    for name in libs:
        try:
            lg: logging.Logger = logging.getLogger(name)
            lg.setLevel(logging.WARNING)
        except Exception as exc:  # pragma: no cover - defensive logging
            # Best-effort: if getting/setting a logger fails, record at debug level and continue
            logger.debug("Failed to set log level for %s: %s", name, exc)
