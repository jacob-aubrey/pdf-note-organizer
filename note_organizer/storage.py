"""SQLite is the source of truth; Word files are replaceable exports."""
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid
from .search import compile_search, normalize


def canonical(path):
    return os.path.normcase(str(Path(path).resolve()))


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest_file(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def entry_sort_key(entry):
    rect = entry["rect"]
    return (entry["path"].casefold(), entry["page"], tuple(entry.get("order", (rect[1], rect[0], 0))), rect[1], rect[0])


DEFAULT_SETTINGS = {"grouping": "Nearby blocks", "gap": 24, "ocr": False,
                    "context_padding": 36, "notebook_style": "Reading"}

SEARCH_FIELDS = {
    "title": "Paper title", "quote": "Highlights and marked text",
    "comment": "Typed notes and replies", "ocr": "Handwriting transcription (OCR)",
    "context": "Surrounding printed text", "filename": "Filename",
    "author": "Author", "doi": "DOI", "color": "Annotation color", "page": "Page number",
}
NOTE_TYPES = ("All notes", "Highlights and markup", "Drawings and handwriting", "Typed notes")


def matches_search(entry, query, fields, match_mode, note_type, matcher=None):
    kind = entry.get("kind", "")
    if note_type == "Highlights and markup" and kind not in {"highlight", "underline", "strikeout", "squiggly"}:
        return False
    if note_type == "Drawings and handwriting" and kind != "drawing":
        return False
    if note_type == "Typed notes" and not entry.get("comment"):
        return False
    matcher = matcher or compile_search(query, match_mode)
    meta = entry.get("metadata", {})
    values = {**{key: entry.get(key, "") for key in ("quote", "comment", "ocr", "context", "color")},
              "title": meta.get("title") or Path(entry["path"]).stem,
              "filename": Path(entry["path"]).name, "author": meta.get("author", ""),
              "doi": meta.get("doi", ""), "page": f"{entry.get('label', '')} {entry.get('page', '')}"}
    haystacks = [normalize(values.get(key, "")) for key in fields]
    return matcher(haystacks)


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY, root TEXT UNIQUE NOT NULL,
                    output TEXT NOT NULL, settings TEXT NOT NULL,
                    dirty INTEGER NOT NULL DEFAULT 1, export_hash TEXT DEFAULT '',
                    exported_at TEXT DEFAULT '', error TEXT DEFAULT '');
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    path TEXT NOT NULL, digest TEXT NOT NULL, signature TEXT NOT NULL,
                    settings TEXT NOT NULL, metadata TEXT NOT NULL, scanned_at TEXT NOT NULL,
                    missing INTEGER DEFAULT 0, UNIQUE(project_id,path));
                CREATE TABLE IF NOT EXISTS entries (
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    key TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(document_id,key));
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    key TEXT NOT NULL, action TEXT NOT NULL, at TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS scan_errors (
                    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
                    path TEXT NOT NULL, error TEXT NOT NULL, at TEXT NOT NULL,
                    PRIMARY KEY(project_id,path));
                CREATE INDEX IF NOT EXISTS document_project ON documents(project_id);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def projects(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM projects ORDER BY root")]

    def preference(self, key, default=None):
        with self.connect() as db:
            row = db.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
        try:
            return json.loads(row[0]) if row else default
        except (ValueError, TypeError):
            return default

    def set_preference(self, key, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO preferences(key,value) VALUES(?,?)", (key, json.dumps(value)))

    def project(self, project_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            return dict(row) if row else None

    def add_project(self, root, output=None):
        root = canonical(root)
        output = output or str(Path(root) / f"Notes on {Path(root).name}.generated.docx")
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO projects(root,output,settings) VALUES(?,?,?)",
                       (root, str(output), json.dumps(DEFAULT_SETTINGS, sort_keys=True)))
            return db.execute("SELECT id FROM projects WHERE root=?", (root,)).fetchone()[0]

    def remove_project(self, project_id):
        with self.connect() as db:
            db.execute("DELETE FROM projects WHERE id=?", (project_id,))

    def set_settings(self, project_id, settings):
        with self.connect() as db:
            db.execute("UPDATE projects SET settings=? WHERE id=?",
                       (json.dumps(settings, sort_keys=True), project_id))
            db.execute("UPDATE projects SET dirty=1 WHERE id=?", (project_id,))

    def mark_dirty(self, project_id):
        with self.connect() as db:
            db.execute("UPDATE projects SET dirty=1 WHERE id=?", (project_id,))

    def export_result(self, project_id, file_hash=None, error=""):
        with self.connect() as db:
            if file_hash is not None:
                db.execute("UPDATE projects SET dirty=0,export_hash=?,exported_at=?,error='' WHERE id=?",
                           (file_hash, timestamp(), project_id))
            else:
                db.execute("UPDATE projects SET dirty=1,error=? WHERE id=?", (error, project_id))

    def documents(self, project_id=None):
        with self.connect() as db:
            sql = "SELECT d.*, (SELECT count(*) FROM entries e WHERE e.document_id=d.id) AS count FROM documents d"
            rows = db.execute(sql + (" WHERE project_id=?" if project_id else "") + " ORDER BY path",
                              (project_id,) if project_id else ())
            return [dict(r) for r in rows]

    def document_at(self, project_id, path):
        with self.connect() as db:
            row = db.execute("SELECT * FROM documents WHERE project_id=? AND path=?",
                             (project_id, canonical(path))).fetchone()
            return dict(row) if row else None

    def scan_result(self, project_id, path, error=""):
        with self.connect() as db:
            if error:
                db.execute("INSERT OR REPLACE INTO scan_errors VALUES(?,?,?,?)",
                           (project_id, canonical(path), error, timestamp()))
            else:
                db.execute("DELETE FROM scan_errors WHERE project_id=? AND path=?", (project_id, canonical(path)))

    def errors(self, project_id):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM scan_errors WHERE project_id=?", (project_id,))]

    def save_scan(self, project_id, path, digest, signature, settings, metadata, entries):
        """Replace a complete successful scan in one transaction. Failed scans never erase notes."""
        path = canonical(path)
        with self.connect() as db:
            old = db.execute("SELECT * FROM documents WHERE project_id=? AND path=?", (project_id, path)).fetchone()
            if not old:
                # A unique identical file with a vanished old path is a rename; copies remain independent.
                candidates = db.execute("SELECT * FROM documents WHERE project_id=? AND digest=?",
                                        (project_id, digest)).fetchall()
                candidates = [r for r in candidates if not Path(r["path"]).exists()]
                if len(candidates) == 1:
                    old = candidates[0]
            doc_id = old["id"] if old else str(uuid.uuid4())
            previous = {r["key"]: r["payload"] for r in db.execute(
                "SELECT key,payload FROM entries WHERE document_id=?", (doc_id,))}
            current = {e["key"]: json.dumps(e, sort_keys=True, ensure_ascii=False) for e in entries}
            changed = old is None or old["path"] != path or old["metadata"] != json.dumps(metadata, sort_keys=True) or bool(old["missing"])
            db.execute("""INSERT INTO documents(id,project_id,path,digest,signature,settings,metadata,scanned_at)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET path=excluded.path,digest=excluded.digest,
                signature=excluded.signature,settings=excluded.settings,metadata=excluded.metadata,
                scanned_at=excluded.scanned_at,missing=0""",
                (doc_id, project_id, path, digest, signature, settings, json.dumps(metadata, sort_keys=True), timestamp()))
            counts = {"added": 0, "updated": 0, "removed": 0}
            for key in previous.keys() | current.keys():
                if previous.get(key) == current.get(key):
                    continue
                action = "removed" if key not in current else "added" if key not in previous else "updated"
                counts[action] += 1
                db.execute("INSERT INTO history(document_id,key,action,at,payload) VALUES(?,?,?,?,?)",
                           (doc_id, key, action, timestamp(), current.get(key, previous.get(key))))
            db.execute("DELETE FROM entries WHERE document_id=?", (doc_id,))
            db.executemany("INSERT INTO entries(document_id,key,payload) VALUES(?,?,?)",
                           [(doc_id, key, payload) for key, payload in current.items()])
            if changed or any(counts.values()):
                db.execute("UPDATE projects SET dirty=1 WHERE id=?", (project_id,))
            return counts

    def mark_missing(self, project_id, seen):
        with self.connect() as db:
            for row in db.execute("SELECT path FROM scan_errors WHERE project_id=?", (project_id,)).fetchall():
                if row["path"] not in seen:
                    db.execute("DELETE FROM scan_errors WHERE project_id=? AND path=?", (project_id, row["path"]))
            for row in db.execute("SELECT id,path,missing FROM documents WHERE project_id=?", (project_id,)).fetchall():
                missing = int(row["path"] not in seen)
                if row["missing"] != missing:
                    db.execute("UPDATE documents SET missing=? WHERE id=?", (missing, row["id"]))
                    db.execute("UPDATE projects SET dirty=1 WHERE id=?", (project_id,))

    def entries(self, project_id=None, document_id=None, query="", fields=None,
                match_mode="All words", note_type="All notes"):
        matcher = compile_search(query, match_mode)
        with self.connect() as db:
            sql = "SELECT e.payload,d.path,d.id AS document_id,d.metadata,d.missing FROM entries e JOIN documents d ON d.id=e.document_id WHERE 1=1"
            args = []
            if project_id:
                sql += " AND d.project_id=?"
                args.append(project_id)
            if document_id:
                sql += " AND d.id=?"
                args.append(document_id)
            results = []
            for row in db.execute(sql, args):
                e = json.loads(row["payload"])
                e.update(path=row["path"], document_id=row["document_id"], metadata=json.loads(row["metadata"]), missing=row["missing"])
                if matches_search(e, query, SEARCH_FIELDS if fields is None else fields, match_mode, note_type, matcher):
                    results.append(e)
            return sorted(results, key=entry_sort_key)

    def history(self, document_id):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM history WHERE document_id=? ORDER BY id DESC", (document_id,))]

    def import_legacy(self, paths):
        with self.connect() as db:
            if db.execute("SELECT 1 FROM preferences WHERE key='legacy_imported'").fetchone():
                return
        for path in paths:
            if not Path(path).is_file():
                continue
            try:
                with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as legacy:
                    rows = legacy.execute("SELECT root_path FROM watched_folders").fetchall()
                for (root,) in rows:
                    self.add_project(root)
            except sqlite3.Error:
                import logging
                logging.exception("Cannot import legacy settings from %s", path)
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO preferences VALUES('legacy_imported','1')")
