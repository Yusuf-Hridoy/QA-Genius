"""The standard factors, and how one matrix row becomes a Playwright project.

The device names below are Playwright's own descriptor keys, checked against
the published `deviceDescriptorsSource.json`. A combination Playwright cannot
emulate is not quietly dropped: the row is kept and marked manual-only, so it
still reaches the CSV and the count on the page.
"""

import re

from qagenius.pairwise import Factor, Rule

STANDARD_FACTORS: list[Factor] = [
    Factor("Browser", ("Chrome", "Firefox", "Safari", "Edge")),
    Factor("Device", ("Desktop", "Tablet", "Phone")),
    Factor("Signed in", ("Yes", "No")),
]
STANDARD_RULES: list[Rule] = [
    Rule(
        "Browser",
        "Firefox",
        "Device",
        "Phone",
        "Playwright can't emulate Firefox on mobile devices.",
    ),
    Rule(
        "Browser",
        "Firefox",
        "Device",
        "Tablet",
        "Playwright can't emulate Firefox on mobile devices.",
    ),
    Rule(
        "Browser",
        "Edge",
        "Device",
        "Tablet",
        "Edge tablet profiles aren't available in Playwright.",
    ),
]

# Factors we know how to turn into Playwright settings; anything else is
# carried through as metadata for the team's own fixtures to read.
KNOWN_FACTORS = {"browser", "device", "signed in", "language", "role", "color scheme"}

# (browser, device) -> Playwright device descriptor. Missing pairs are manual.
DEVICE_PROFILES = {
    ("chrome", "desktop"): "Desktop Chrome",
    ("chrome", "phone"): "Pixel 7",
    ("chrome", "tablet"): "Galaxy Tab S4",
    ("safari", "desktop"): "Desktop Safari",
    ("safari", "phone"): "iPhone 14",
    ("safari", "tablet"): "iPad (gen 7)",
    ("firefox", "desktop"): "Desktop Firefox",
    ("edge", "desktop"): "Desktop Edge",
}
CHANNELS = {"edge": "msedge"}

LOCALES = {
    "en": "en-US",
    "bn": "bn-BD",
    "ar": "ar-SA",
    "de": "de-DE",
    "fr": "fr-FR",
    "es": "es-ES",
}
# "en-GB", "pt_BR": already a locale code, so it is used as written.
_LOCALE_CODE = re.compile(r"^[a-z]{2}[-_][A-Za-z]{2,4}$")


def _slug(text: str) -> str:
    """"Payment method" -> "payment_method", for a metadata key."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(text or "").strip().lower())
    return cleaned.strip("_") or "factor"


def _locale_for(value: str) -> str | None:
    written = str(value or "").strip()
    if not written:
        return None
    if _LOCALE_CODE.match(written):
        return written.replace("_", "-")
    return LOCALES.get(written.lower())


def playwright_project(row: dict[str, str]) -> dict:
    """One matrix row as a Playwright project, or a row marked manual-only."""
    lowered = {str(name or "").strip().lower(): value for name, value in row.items()}
    browser = str(lowered.get("browser", "")).strip().lower()
    device = str(lowered.get("device", "Desktop")).strip().lower() or "desktop"

    project: dict = {"name": " · ".join(str(value) for value in row.values())}
    metadata: dict[str, str] = {}

    profile = DEVICE_PROFILES.get((browser, device))
    if browser and profile is None:
        # Edge on a phone, Firefox on a tablet: real combinations to test, but
        # not ones Playwright can drive.
        project["manual_only"] = True
    else:
        project["device"] = profile or "Desktop Chrome"
        if browser in CHANNELS:
            project["channel"] = CHANNELS[browser]

    role = lowered.get("role")
    if role:
        metadata["role"] = str(role)

    signed_in = str(lowered.get("signed in", "")).strip().lower()
    if signed_in in ("yes", "true", "signed in"):
        who = _slug(role) if role else "user"
        project["storageState"] = f"auth/{who}.json"

    language = lowered.get("language")
    if language:
        locale = _locale_for(language)
        if locale:
            project["locale"] = locale
        else:
            metadata["language"] = str(language)

    scheme = str(lowered.get("color scheme", "")).strip().lower()
    if scheme in ("light", "dark"):
        project["colorScheme"] = scheme

    for name, value in row.items():
        if str(name or "").strip().lower() in KNOWN_FACTORS:
            continue
        metadata[_slug(name)] = str(value)

    if metadata:
        project["metadata"] = metadata
    return project
