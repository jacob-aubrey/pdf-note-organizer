"""Private feedback drafts and read-only, manual GitHub release checks.

No credentials, library details, files, or automatic installation belong here.
Browser/email handoff is deliberately left to the explicit UI actions.
"""
from dataclasses import dataclass
import json
import platform
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen

from . import APP_NAME, __version__


REPOSITORY = "jacob-aubrey/pdf-note-organizer"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
RELEASES_URL = f"{REPOSITORY_URL}/releases"
RELEASE_API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
FEEDBACK_DESTINATION = "aubrey.jd00@gmail.com"
REQUEST_TIMEOUT = 10
MAX_RESPONSE_BYTES = 2_000_000


def environment_summary(version=None, *, frozen=None, system=None, release=None):
    """The complete, small allowlist of information added to a feedback draft."""
    return {
        "App version": __version__ if version is None else str(version),
        "Operating system": " ".join(filter(None, [platform.system() if system is None else system,
                                                    platform.release() if release is None else release])),
        "Install type": "Packaged application" if (getattr(sys, "frozen", False) if frozen is None else frozen)
                        else "Source code",
    }


def feedback_report(kind, title, description, environment=None):
    """Use only reviewed user text and explicitly allowlisted environment fields."""
    environment = environment_summary() if environment is None else environment
    details = "\n".join(f"{label}: {environment.get(label, 'Unknown')}" for label in
                        ("App version", "Operating system", "Install type"))
    return f"{APP_NAME} — {kind}\n{title.strip()}\n\n{description.strip()}\n\n{details}"


def feedback_destination(destination):
    """Return ('email' or 'form', address), accepting no injected mail headers."""
    destination = str(destination or "").strip()
    if not destination or any(character in destination for character in "\r\n"):
        return None
    if destination.startswith("mailto:"):
        destination = destination[7:]
    if re.fullmatch(r"[^\s@<>?&#:/]+@[^\s@<>?&#:/]+\.[^\s@<>?&#:/]+", destination):
        return "email", destination
    try:
        parsed = urlsplit(destination)
        if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
            return "form", destination
    except ValueError:
        pass
    return None


def feedback_handoff(destination, title, report):
    """Prepare a private destination URL; this never opens it or sends a report.

    Mail clients commonly limit URL length. The UI copies the complete report
    first, so long drafts use a short paste instruction instead of truncation.
    """
    target = feedback_destination(destination)
    if not target:
        raise ValueError("A private feedback email address or HTTPS form is required.")
    kind, address = target
    if kind == "form":
        return address
    subject = " ".join(title.splitlines()).strip()[:180] or f"{APP_NAME} feedback"
    prefix = "mailto:" + quote(address, safe="@.")
    url = prefix + "?" + urlencode({"subject": subject, "body": report}, quote_via=quote)
    if len(url) > 1800:
        url = prefix + "?" + urlencode({"subject": subject,
            "body": "The complete feedback report has been copied to your clipboard. Paste it here before sending."},
            quote_via=quote)
    return url


_VERSION = re.compile(
    r"^v?(\d+(?:\.\d+){0,3})(?:[-_.]?(dev|a|alpha|b|beta|rc|pre|preview|post|rev|r)[-_.]?(\d*))?"
    r"(?:\+[a-z0-9]+(?:[-_.][a-z0-9]+)*)?$", re.IGNORECASE)
_PHASES = {"dev": -1, "a": 0, "alpha": 0, "b": 1, "beta": 1,
           "pre": 2, "preview": 2, "rc": 2, "post": 4, "rev": 4, "r": 4}


def version_key(value):
    """Numeric release ordering, with common prerelease/postrelease suffixes.

    Unknown naming schemes are not guessed: the UI can offer the release page
    without claiming that an unrecognized tag is newer than the installed app.
    """
    match = _VERSION.fullmatch(str(value).strip())
    if not match:
        return None
    numbers = tuple(int(component) for component in match[1].split("."))
    return numbers + (0,) * (4 - len(numbers)), _PHASES.get((match[2] or "").lower(), 3), int(match[3] or 0)


def _github_url(value, path_prefix):
    try:
        parsed = urlsplit(str(value or ""))
        path = unquote(parsed.path).replace("\\", "/")
        if (parsed.scheme == "https" and parsed.netloc == "github.com" and not parsed.query
                and not parsed.fragment and not {".", ".."}.intersection(path.split("/"))
                and path.startswith(f"/{REPOSITORY}/{path_prefix}")):
            return str(value)
    except ValueError:
        pass
    return ""


def release_asset(assets, *, system=None, machine=None):
    """Choose a compatible packaged Windows asset, never a source ZIP."""
    if (platform.system() if system is None else system).lower() != "windows":
        return ""
    machine = (platform.machine() if machine is None else machine).lower()
    arm = "arm" in machine or "aarch" in machine
    bits64 = "64" in machine
    candidates = []
    for asset in assets if isinstance(assets, list) else []:
        if not isinstance(asset, dict) or asset.get("state", "uploaded") != "uploaded":
            continue
        name = str(asset.get("name", "")).lower()
        url = _github_url(asset.get("browser_download_url"), "releases/download/")
        if not url or not name.endswith((".exe", ".msi")):
            continue
        asset_arm = bool(re.search(r"arm64|aarch64|arm32|armv7", name))
        asset_64 = bool(re.search(r"x64|amd64|win64|x86_64", name))
        asset_32 = bool(re.search(r"win32|i[3-6]86|x86(?!_64)", name))
        if (asset_arm and not arm) or (asset_64 and (arm or not bits64)) or (asset_32 and arm):
            continue
        architecture = asset_arm if arm else asset_64 if bits64 else asset_32
        installer = bool(re.search(r"setup|install", name)) or name.endswith(".msi")
        candidates.append((architecture, installer, name, url))
    return max(candidates)[-1] if candidates else ""


@dataclass(frozen=True)
class UpdateResult:
    state: str
    current_version: str
    message: str
    latest_version: str = ""
    notes: str = ""
    release_url: str = RELEASES_URL
    download_url: str = ""
    download_label: str = ""


def release_result(release, current_version=__version__, *, frozen=False, system=None, machine=None):
    """Interpret a public release without acting on any URLs in its notes."""
    current_version = str(current_version)
    if not isinstance(release, dict):
        return UpdateResult("error", current_version, "GitHub returned an unreadable release response. Try again later.")
    tag = str(release.get("tag_name") or "").strip()
    latest = version_key(tag)
    if release.get("draft") or release.get("prerelease") or latest and latest[1] < 3:
        return UpdateResult("no_release", current_version, "No published stable release is available from this check.")
    release_url = _github_url(release.get("html_url"), "releases/tag/") or RELEASES_URL
    notes = str(release.get("body") or "No release notes were provided.")
    current = version_key(current_version)
    if not latest or not current:
        return UpdateResult("unrecognized", current_version,
            "A release was found, but its version cannot be compared automatically. Review the release page.",
            tag, notes, release_url)
    state = "update" if latest > current else "current" if latest == current else "ahead"
    message = {"update": f"{APP_NAME} {tag} is available. You are using {current_version}.",
               "current": f"You are using the latest published stable version ({current_version}).",
               "ahead": f"You are using {current_version}, newer than the latest published stable release ({tag})."}[state]
    download = label = ""
    if state == "update":
        if frozen:
            download = release_asset(release.get("assets"), system=system, machine=machine)
            label = "Download update…" if download else ""
            if not download:
                message += " No compatible Windows installer is attached; review the release page."
        else:
            download = f"{REPOSITORY_URL}/archive/refs/tags/{quote(tag, safe='')}.zip"
            label = "Download source…"
    return UpdateResult(state, current_version, message, tag, notes, release_url, download, label)


def check_updates(current_version=__version__, *, frozen=None, timeout=REQUEST_TIMEOUT, opener=None):
    """Read public release metadata once; never download or install an update."""
    current_version = str(current_version)
    request = Request(RELEASE_API_URL, headers={"Accept": "application/vnd.github+json",
        "User-Agent": f"Notable-update-check/{current_version}", "X-GitHub-Api-Version": "2026-03-10"})
    try:
        with (urlopen if opener is None else opener)(request, timeout=timeout) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise ValueError("Release response is too large")
        release = json.loads(data)
    except HTTPError as error:
        if error.code == 404:
            return UpdateResult("no_release", current_version,
                "No public stable release was found. The repository may not have a published release yet.")
        message = "GitHub temporarily limited update checks. Try again later." if error.code in {403, 429} else \
                  "GitHub could not complete the update check. Try again later."
        return UpdateResult("error", current_version, message)
    except (URLError, TimeoutError, OSError):
        return UpdateResult("error", current_version, "Could not reach GitHub. Check your connection and try again.")
    except (ValueError, TypeError, UnicodeError):
        return UpdateResult("error", current_version, "GitHub returned an unreadable release response. Try again later.")
    return release_result(release, current_version,
        frozen=getattr(sys, "frozen", False) if frozen is None else frozen)
