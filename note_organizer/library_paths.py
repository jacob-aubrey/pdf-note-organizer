"""Choose one library consistently and describe other libraries without modifying them."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys


def project_root():
    return Path(__file__).resolve().parent.parent


def source_data_directory(source_root=None):
    root = Path(source_root) if source_root is not None else project_root()
    # Preserve embedded absolute source paths in the existing workspace library.
    # Fresh, independent checkouts continue to use their own .local-data.
    previous = root.parent / '.local-data'
    if root.name == 'Notable' and (root.parent / 'remarkable-zotero').is_dir() and previous.is_dir():
        return previous.resolve()
    return (root / '.local-data').resolve()


def installed_data_directory(environ=None):
    environ = os.environ if environ is None else environ
    return (Path(environ.get("LOCALAPPDATA") or Path.home()) / "PDF Note Organizer").resolve()


def resolve_data_directory(source_root=None, *, environ=None, frozen=None):
    """Explicit overrides win; every source launch uses the project library."""
    environ = os.environ if environ is None else environ
    if environ.get("PDF_NOTES_DATA_DIR"):
        return Path(environ["PDF_NOTES_DATA_DIR"]).expanduser().resolve()
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if frozen:
        return installed_data_directory(environ)
    return source_data_directory(source_root)


def should_import_legacy(data, source_root=None, *, environ=None):
    """Development libraries stay isolated unless legacy import is explicitly enabled."""
    environ = os.environ if environ is None else environ
    if "PDF_NOTES_SKIP_LEGACY_IMPORT" in environ:
        return environ["PDF_NOTES_SKIP_LEGACY_IMPORT"] != "1"
    source_root = Path(source_root) if source_root is not None else project_root()
    return Path(data).resolve() != source_data_directory(source_root)


def inspect_library(data):
    """Return a small read-only summary; never read pairing credentials or note text."""
    data = Path(data).resolve()
    database = data / "library.sqlite3"
    summary = {"path": str(data), "exists": database.is_file(), "configured": False,
               "projects": 0, "documents": 0, "notes": 0, "cloud_items": 0,
               "paired": (data / "remarkable" / "device-token.dpapi").is_file(),
               "cloud_source": "", "pc_root": "", "error": ""}
    if not summary["exists"]:
        return summary
    try:
        # mode=ro avoids creating or migrating a second library during diagnostics.
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0.25)) as db:
            db.execute("PRAGMA query_only=ON")
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for key, table in (("projects", "projects"), ("documents", "documents"),
                               ("notes", "entries"), ("cloud_items", "remarkable_items")):
                if table in tables:
                    summary[key] = db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            if "preferences" in tables:
                row = db.execute("SELECT value FROM preferences WHERE key='remarkable'").fetchone()
                config = json.loads(row[0]) if row else {}
                if isinstance(config, dict):
                    summary["cloud_source"] = config.get("source_folder_name", "")
                    summary["pc_root"] = config.get("pc_root", "")
            summary["configured"] = bool(summary["projects"] or summary["documents"]
                                         or summary["cloud_items"] or summary["pc_root"])
    except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
        summary["error"] = f"Unable to inspect this library: {exc}"
    return summary


def library_diagnostics(active_data, source_root=None, *, environ=None):
    """Identify the active library and any existing project/installed alternatives."""
    source_root = Path(source_root) if source_root is not None else project_root()
    project_data = source_data_directory(source_root)
    installed_data = installed_data_directory(environ)
    active_data = Path(active_data).resolve()
    known = {project_data: "Project library", installed_data: "Installed app library"}

    def describe(path):
        return {**inspect_library(path), "name": known.get(path, "Custom library")}

    return {"active": describe(active_data),
            "alternatives": [describe(path) for path in dict.fromkeys((project_data, installed_data))
                             if path != active_data and (path / "library.sqlite3").is_file()]}
