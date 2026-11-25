"""Nomadic dashboard links: Workbench for saved recordings, account pages for station setup."""

from urllib.parse import SplitResult, quote, urlencode, urlsplit, urlunsplit

# Tells Nomadic that the account was created from a LABS station
SIGNUP_PARTNER = "franka-labs"
API_KEYS_PAGE = "/profile?tab=apiKeys"


def _dashboard(dashboard_url: str) -> SplitResult:
    parsed = urlsplit(dashboard_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("The Nomadic dashboard address must be an HTTPS URL without credentials.")
    return parsed


def _link(dashboard: SplitResult, path: str, query: dict[str, str]) -> str:
    return urlunsplit((dashboard.scheme, dashboard.netloc, f"{dashboard.path.rstrip('/')}{path}", urlencode(query), ""))


def workbench_url(dashboard_url: str, batch_id: str | None, video_id: str) -> str:
    """Build a Workbench link for the saved recording."""
    target = quote(batch_id, safe="") if batch_id else f"videos/{quote(video_id, safe='')}"
    return _link(_dashboard(dashboard_url), f"/workbench/{target}", {"video": video_id})


def signup_url(dashboard_url: str) -> str:
    """Link to Nomadic sign-up that continues to the API keys page."""
    return _link(_dashboard(dashboard_url), "/signup", {"partner": SIGNUP_PARTNER, "returnTo": API_KEYS_PAGE})


def api_keys_url(dashboard_url: str) -> str:
    """Link to the API keys page for an existing Nomadic account."""
    return _link(_dashboard(dashboard_url), "/profile", {"tab": "apiKeys"})


def billing_url(dashboard_url: str) -> str:
    """Link to the account's billing page, to top up credits or enable uploads."""
    return _link(_dashboard(dashboard_url), "/profile", {"tab": "billing"})
