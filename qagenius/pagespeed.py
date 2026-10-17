"""Google PageSpeed Insights, the only network call QA-Genius makes.

The server talks to googleapis.com and nothing else: the page being measured is
a query parameter Google fetches, never a URL this server opens. Private and
local addresses are refused before any call, because Google could not reach
them anyway and the refusal should be instant.

No AI, no key of the user's AI providers, and the PageSpeed key is never
logged or echoed back.
"""

import ipaddress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

PSI_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
TIMEOUT_S = 90
MAX_URL = 2000

# Documented enum values are upper case (Strategy, Category).
STRATEGIES = {"mobile": "MOBILE", "desktop": "DESKTOP"}

PRIVATE_URL_ERROR = (
    "PageSpeed can only measure public pages. For localhost or private "
    "staging, use the k6 export instead."
)
TIMEOUT_ERROR = "PageSpeed took too long. Try again or try desktop."
NO_KEY_ERROR = (
    "PageSpeed refused the request. Google's keyless quota is zero, so this "
    "needs a free Google API key — add one below and try again."
)
RATE_LIMIT_ERROR = (
    "PageSpeed is rate-limited right now. Try again in a minute, or use a key "
    "with more quota."
)

# lab metric id -> (audit id, the unit Lighthouse reports it in)
LAB_AUDITS = {
    "lcp": ("largest-contentful-paint", "millisecond"),
    "cls": ("cumulative-layout-shift", "unitless"),
    "fcp": ("first-contentful-paint", "millisecond"),
    "ttfb": ("server-response-time", "millisecond"),
    "weight": ("total-byte-weight", "byte"),
    "tbt": ("total-blocking-time", "millisecond"),
}
# field metric id -> (CrUX key, divisor). CLS arrives as an integer x100.
FIELD_METRICS = {
    "lcp": ("LARGEST_CONTENTFUL_PAINT_MS", 1),
    "inp": ("INTERACTION_TO_NEXT_PAINT", 1),
    "cls": ("CUMULATIVE_LAYOUT_SHIFT_SCORE", 100),
}
BYTES_PER_KB = 1024


@dataclass(frozen=True)
class Measurement:
    url: str
    strategy: str  # "mobile" | "desktop"
    lab: dict[str, float] = field(default_factory=dict)
    field: dict[str, float] = field(default_factory=dict)
    performance_score: int | None = None
    fetched_at: str = ""


class PageSpeedError(Exception):
    """Something a user can read and act on. Never carries the API key."""


def validate_public_url(url: str) -> str | None:
    """None when PageSpeed could reach this, else the reason to show."""
    cleaned = (url or "").strip()
    if not cleaned:
        return "Paste the address of the page you want measured."
    if len(cleaned) > MAX_URL:
        return f"That URL is longer than {MAX_URL} characters."
    parts = urlsplit(cleaned)
    if parts.scheme.lower() not in ("http", "https"):
        return "The address has to start with http:// or https://."
    host = (parts.hostname or "").strip().lower()
    if not host:
        return "That address has no host name."
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return PRIVATE_URL_ERROR
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return None  # a name, and not one of the local ones
    # Covers 127.*, 10.*, 172.16-31.*, 192.168.*, ::1, 169.254.* and 0.0.0.0.
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_unspecified
        or address.is_reserved
    ):
        return PRIVATE_URL_ERROR
    return None


def _numeric(audits: dict, audit_id: str) -> float | None:
    audit = audits.get(audit_id)
    if not isinstance(audit, dict):
        return None
    value = audit.get("numericValue")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _lab(lighthouse: dict) -> dict[str, float]:
    audits = lighthouse.get("audits")
    if not isinstance(audits, dict):
        return {}
    lab: dict[str, float] = {}
    for metric_id, (audit_id, _unit) in LAB_AUDITS.items():
        value = _numeric(audits, audit_id)
        if value is None:
            continue
        # Lighthouse reports page weight in bytes; the budget is in KB.
        lab[metric_id] = value / BYTES_PER_KB if metric_id == "weight" else value
    return lab


def _field(loading: dict) -> dict[str, float]:
    metrics = loading.get("metrics") if isinstance(loading, dict) else None
    if not isinstance(metrics, dict):
        return {}
    found: dict[str, float] = {}
    for metric_id, (key, divisor) in FIELD_METRICS.items():
        entry = metrics.get(key)
        if not isinstance(entry, dict):
            continue
        value = entry.get("percentile")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        found[metric_id] = float(value) / divisor
    return found


def _score(lighthouse: dict) -> int | None:
    categories = lighthouse.get("categories")
    if not isinstance(categories, dict):
        return None
    performance = categories.get("performance")
    if not isinstance(performance, dict):
        return None
    score = performance.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    # Lighthouse scores run 0-1; people read them out of 100.
    return round(float(score) * 100)


def _short_reason(payload: dict) -> str:
    """The one sentence worth repeating out of Google's error."""
    lighthouse = payload.get("lighthouseResult")
    if isinstance(lighthouse, dict):
        message = lighthouse.get("runtimeError")
        if isinstance(message, dict) and isinstance(message.get("message"), str):
            return message["message"].strip()[:200]
    error = payload.get("error")
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return error["message"].strip()[:200]
    return "no reason given"


def parse(payload: dict, url: str, strategy: str) -> Measurement:
    """A PSI response as the numbers the budget is compared against."""
    lighthouse = payload.get("lighthouseResult")
    lighthouse = lighthouse if isinstance(lighthouse, dict) else {}
    return Measurement(
        url=url,
        strategy=strategy,
        lab=_lab(lighthouse),
        field=_field(payload.get("loadingExperience") or {}),
        performance_score=_score(lighthouse),
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def measure(
    url: str,
    strategy: str = "mobile",
    api_key: str | None = None,
    client=None,
) -> Measurement:
    """Measure one public page. Raises PageSpeedError with a readable message."""
    reason = validate_public_url(url)
    if reason:
        raise PageSpeedError(reason)
    wanted = STRATEGIES.get((strategy or "").lower())
    if wanted is None:
        raise PageSpeedError("Choose mobile or desktop.")

    params = {"url": url.strip(), "strategy": wanted, "category": "PERFORMANCE"}
    if (api_key or "").strip():
        params["key"] = api_key.strip()

    owned = client is None
    client = client or httpx.Client(timeout=TIMEOUT_S)
    try:
        response = client.get(PSI_URL, params=params)
    except httpx.TimeoutException as error:
        raise PageSpeedError(TIMEOUT_ERROR) from error
    except httpx.HTTPError as error:
        # Never interpolate the request: it carries the key.
        raise PageSpeedError("Could not reach PageSpeed. Try again.") from error
    finally:
        if owned:
            client.close()

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    status = response.status_code
    if status == 429:
        raise PageSpeedError(RATE_LIMIT_ERROR if api_key else NO_KEY_ERROR)
    if status >= 400:
        raise PageSpeedError(f"PageSpeed couldn't load that page: {_short_reason(payload)}")
    if not payload.get("lighthouseResult"):
        raise PageSpeedError(f"PageSpeed couldn't load that page: {_short_reason(payload)}")
    return parse(payload, url.strip(), (strategy or "").lower())
