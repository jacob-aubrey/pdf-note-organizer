"""Small read-only library snapshots; Tk never waits for a database writer."""
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3

from .storage import DEFAULT_SETTINGS
from .remarkable_sync import default_config, folder_destination, scoped_folders
from .paper_projection import (load_paper_sources, annotated_documents, lightweight_note_fingerprints,
                               project_papers)


class LibraryView:
    def __init__(self, path, preferences=None, projects=(), documents=(), errors=(), cloud_items=None,
                 directories=(), files=(), source_links=None, entry_fingerprints=()):
        self.path = Path(path)
        self.preferences = preferences or {}
        self.project_rows = list(projects)
        self.raw_document_rows = annotated_documents(documents, source_links or {})
        self.document_rows = project_papers(self.raw_document_rows, entry_fingerprints)
        self.error_rows = list(errors)
        self.cloud_items = cloud_items or {}
        self.directories, self.files = set(directories), set(files)
        self.project_index = {row["id"]: row for row in self.project_rows}

    def preference(self, key, default=None):
        return self.preferences.get(key, default)

    def projects(self):
        return self.project_rows

    def project(self, project_id):
        return self.project_index.get(project_id)

    def documents(self, project_id=None):
        return [row for row in self.document_rows if project_id is None or row["project_id"] == project_id]

    def errors(self, project_id):
        return [row for row in self.error_rows if row["project_id"] == project_id]

    def remarkable_items(self):
        return self.cloud_items

    def default_settings(self):
        saved = self.preference("default_settings", {})
        return {**DEFAULT_SETTINGS, **{k: v for k, v in saved.items() if k in DEFAULT_SETTINGS}} if isinstance(saved, dict) else dict(DEFAULT_SETTINGS)

    def note_token(self, project_id=None, document_id=None):
        # Cloud metadata and export status do not invalidate the reader's query.
        def document_token(document):
            return (document["id"], document["path"], document["digest"], document["settings"], document["metadata"],
                    document["missing"], document["count"], document.get("note_revision", 0))
        raw_by_id = {document["id"]: document for document in self.raw_document_rows}
        tokens = []
        for document in self.document_rows:
            if project_id is not None and document["project_id"] != project_id:
                continue
            variant_ids = document.get("variant_document_ids", [document["id"]])
            if document_id is not None and document_id not in variant_ids:
                continue
            token = document_token(document)
            if document.get("logical_paper_id"):
                variants = []
                for variant_id in variant_ids:
                    variant = raw_by_id[variant_id]
                    source = variant["paper_source"]
                    metadata = source["metadata"]
                    proof = (source.get("digest"), metadata.get("role"), metadata.get("cloud_id"),
                             metadata.get("page_mapping_identity"), metadata.get("original_pdf_digest"),
                             source.get("cloud_original_digest"))
                    variants.append(document_token(variant) + (proof,))
                token += (document["logical_paper_id"], document["logical_paper_title"], tuple(variants))
            tokens.append(token)
        return tuple(tokens)


def read_view(path):
    """Read one consistent lightweight snapshot, with a short lock timeout."""
    path = Path(path)
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=.15)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        preferences = {}
        for row in db.execute("SELECT key,value FROM preferences"):
            try:
                preferences[row["key"]] = json.loads(row["value"])
            except (ValueError, TypeError):
                continue
        projects = [dict(row) for row in db.execute("SELECT * FROM projects ORDER BY root")]
        documents = [dict(row) for row in db.execute("SELECT d.*, (SELECT count(*) FROM entries e WHERE e.document_id=d.id) AS count FROM documents d WHERE hidden=0 ORDER BY path")]
        source_links = load_paper_sources(db)
        entry_fingerprints = lightweight_note_fingerprints(db, annotated_documents(documents, source_links))
        errors = [dict(row) for row in db.execute("SELECT * FROM scan_errors")]
        items = {row["id"]: json.loads(row["payload"]) for row in db.execute("SELECT * FROM remarkable_items")}
    # Directory and retained-file probes also belong off the interface thread.
    config = {**default_config(path.parent), **preferences.get("remarkable", {})}
    roots = {p["root"] for p in projects} | {config["pc_root"]} | set(config.get("mappings", {}).values())
    directories = {root for root in roots if root and Path(root).is_dir()}
    candidates = {path.parent / "remarkable" / "device-token.dpapi"}
    candidates.update(Path(item["review_pdf"]) for item in items.values() if item.get("review_pdf"))
    files = {str(file) for file in candidates if file.is_file()}
    return LibraryView(path, preferences, projects, documents, errors, items, directories, files,
                       source_links, entry_fingerprints)


def cloud_destinations(catalog, config, data_dir):
    """Resolve draft folder routing without blocking Tk on disk or OneDrive."""
    config = deepcopy(config)
    excluded = [Path(config["review_dir"]).resolve(), (Path(data_dir) / "remarkable").resolve()]
    result = {}
    for folder in scoped_folders(catalog, config.get("source_folder_id", "")):
        target = folder_destination(folder, catalog, config)
        result[folder["id"]] = str(target) if target and not any(target.is_relative_to(root) for root in excluded) else "Needs mapping"
    root = config["pc_root"]
    return result, bool(root and Path(root).is_dir())
