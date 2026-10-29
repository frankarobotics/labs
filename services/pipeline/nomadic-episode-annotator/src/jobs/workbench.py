"""Nomadic Workbench links for saved recordings."""

from urllib.parse import quote, urlencode, urlsplit, urlunsplit


def workbench_url(dashboard_url: str, batch_id: str | None, video_id: str) -> str:
    """Build a Workbench link for the saved recording."""
    parsed = urlsplit(dashboard_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("The Nomadic dashboard address must be an HTTPS URL without credentials.")
    target = quote(batch_id, safe="") if batch_id else f"videos/{quote(video_id, safe='')}"
    path = f"{parsed.path.rstrip('/')}/workbench/{target}"
    return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode({"video": video_id}), ""))
