"""The Nomadic API key an operator connected from the episode page, kept beside the job store."""

import json
import os
from pathlib import Path

FILE_NAME = "station_key.json"


def load(state_path: Path) -> tuple[str, str | None] | None:
    """Return the saved key and its account email, or None when the station was never connected."""
    try:
        saved = json.loads((state_path / FILE_NAME).read_text())
    except FileNotFoundError:
        return None
    return str(saved["api_key"]), saved.get("email")


def save(state_path: Path, api_key: str, email: str | None) -> None:
    """Write the key readable by the annotator only, replacing the file atomically."""
    state_path.mkdir(parents=True, exist_ok=True)
    partial = state_path / f"{FILE_NAME}.partial"
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump({"api_key": api_key, "email": email}, handle)
    partial.replace(state_path / FILE_NAME)


def remove(state_path: Path) -> None:
    """Forget the connected key, for example when the worker could not start with it."""
    (state_path / FILE_NAME).unlink(missing_ok=True)
