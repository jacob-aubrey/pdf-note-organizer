"""
PDF Note Watcher & Exporter — Edge-compatible, no-dup comments, clustered ink

Fixes and features:
- Robust highlight text extraction using QuadPoints with word-order stitching.
- Pair comments with highlights via IRT and popups.
- Skip exporting reply "Text" notes (already merged into parent), and de-duplicate merged strings.
- Cluster ink strokes into composite drawings; one snapshot per cluster.
"""

import os
import sys
import time
import logging
import threading
import hashlib
import sqlite3
import queue
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from collections import defaultdict
import math

# Third-party imports
try:
    import fitz  # PyMuPDF
except ImportError:
    print("Error: PyMuPDF (fitz) not found. Please install: pip install pymupdf")
    sys.exit(1)

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("Error: watchdog not found. Please install: pip install watchdog")
    sys.exit(1)

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Optional OCR support
try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("Optional: PIL or pytesseract not found. OCR for ink annotations will be disabled.")
    print("Install with: pip install pillow pytesseract")

# Optional Word / .docx support
try:
    from docx import Document
    from docx.shared import Inches
    from docx.text.paragraph import Paragraph
    from docx.oxml import OxmlElement
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    print("Error: python-docx not found. Please install: pip install python-docx")
    sys.exit(1)


def resource_path(relative_path: str) -> str:
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

# =========================
# Configuration
# =========================

DB_PATH = "notes_watcher.db"
SCAN_DEBOUNCE_SECONDS = 2.0
VALID_EXTENSIONS = {".pdf"}

# =========================
# SQLite Database Helper
# =========================

class Database:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS watched_folders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    root_path TEXT NOT NULL UNIQUE,
                    notes_path TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS pdfs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pdf_id TEXT NOT NULL,
                    root_id INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    last_seen_mtime REAL NOT NULL,
                    UNIQUE(pdf_id),
                    FOREIGN KEY(root_id) REFERENCES watched_folders(id) ON DELETE CASCADE
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS annotations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pdf_id INTEGER NOT NULL,
                    annot_key TEXT NOT NULL,
                    created_at TEXT,
                    content_hash TEXT NOT NULL,
                    UNIQUE(pdf_id, annot_key),
                    FOREIGN KEY(pdf_id) REFERENCES pdfs(id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def _get_conn(self):
        return sqlite3.connect(self.path, check_same_thread=False)

    # Watched Folders
    def add_watched_folder(self, root_path: str, notes_path: str):
        with self._lock, self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT OR IGNORE INTO watched_folders (root_path, notes_path) VALUES (?, ?)",
                (root_path, notes_path),
            )
            conn.commit()

    def remove_watched_folder(self, root_path: str):
        with self._lock, self._get_conn() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM watched_folders WHERE root_path = ?", (root_path,))
            conn.commit()

    def get_watched_folders(self):
        with self._lock, self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT id, root_path, notes_path FROM watched_folders")
            return c.fetchall()

    def get_watched_folder_by_path(self, root_path: str):
        with self._lock, self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT id, root_path, notes_path FROM watched_folders WHERE root_path = ?",
                (root_path,),
            )
            return c.fetchone()

    # PDFs
    def upsert_pdf(self, pdf_id: str, root_id: int, path: str, mtime: float):
        with self._lock, self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                """
                INSERT INTO pdfs (pdf_id, root_id, path, last_seen_mtime)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(pdf_id) DO UPDATE SET
                    root_id=excluded.root_id,
                    path=excluded.path,
                    last_seen_mtime=excluded.last_seen_mtime
                """,
                (pdf_id, root_id, path, mtime),
            )
            conn.commit()
            c.execute("SELECT id FROM pdfs WHERE pdf_id = ?", (pdf_id,))
            row = c.fetchone()
            return row[0] if row else None

    # Annotations
    def annotation_exists(self, pdf_db_id: int, annot_key: str) -> bool:
        with self._lock, self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT 1 FROM annotations WHERE pdf_id = ? AND annot_key = ?",
                (pdf_db_id, annot_key),
            )
            return c.fetchone() is not None

    def insert_annotation(self, pdf_db_id: int, annot_key: str, created_at: str, content_hash: str):
        with self._lock, self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                """
                INSERT OR IGNORE INTO annotations (pdf_id, annot_key, created_at, content_hash)
                VALUES (?, ?, ?, ?)
                """,
                (pdf_db_id, annot_key, created_at, content_hash),
            )
            conn.commit()

# =========================
# Utilities
# =========================

def is_pdf(path: str) -> bool:
    return Path(path).suffix.lower() in VALID_EXTENSIONS

def compute_pdf_id(path: str) -> str | None:
    p = Path(path)
    try:
        size = p.stat().st_size
    except FileNotFoundError:
        return None
    h = hashlib.sha256()
    h.update(str(size).encode("utf-8"))
    try:
        with p.open("rb") as f:
            chunk = f.read(1024 * 1024)
            h.update(chunk)
    except Exception:
        return None
    return h.hexdigest()

def parse_pdf_date(date_str: str) -> str:
    if not date_str:
        return ""
    s = date_str[2:] if date_str.startswith("D:") else date_str
    base = ''.join(ch for ch in s if ch.isdigit())
    if len(base) < 8:
        return ""
    try:
        dt = datetime(int(base[0:4]), int(base[4:6]), int(base[6:8]))
        return dt.strftime("%d-%b-%y")
    except ValueError:
        return ""

def file_mtime_date(path: str) -> str:
    try:
        ts = os.path.getmtime(path)
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%d-%b-%y")
    except Exception:
        return ""

def make_file_uri(path: str, page: int) -> str:
    p = Path(path).resolve()
    drive = p.drive
    if drive:
        rest = p.relative_to(drive + "\\")
        uri_path = quote(str(rest).replace("\\", "/"))
        uri = f"file:///{drive[0]}:/{uri_path}"
    else:
        uri_path = quote(str(p).replace("\\", "/"))
        uri = f"file:///{uri_path}"
    return f"{uri}#page={page}"

def get_media_dir(notes_path: str) -> Path:
    return Path(notes_path).with_name("notes_media")

# =========================
# PDF Annotation Scanner
# =========================

class PDFScanner:
    _GLOBAL_DOC_LOCK = threading.Lock()

    def __init__(self, db: Database):
        self.db = db

    # ---------- highlight extraction ----------
    def _get_highlighted_text(self, page, annot) -> str:
        try:
            rects = []
            verts = getattr(annot, "vertices", None)
            if verts and len(verts) % 4 == 0:
                for i in range(0, len(verts), 4):
                    quad = verts[i:i+4]
                    def _xy(pt):
                        try:
                            return (pt.x, pt.y)
                        except Exception:
                            return (pt[0], pt[1])
                    xys = [_xy(q) for q in quad]
                    xs = [x for x, _ in xys]
                    ys = [y for _, y in xys]
                    rects.append(fitz.Rect(min(xs), min(ys), max(xs), max(ys)))
            if not rects and annot.rect:
                rects = [annot.rect]
            if not rects:
                return ""

            PAD = 1.5
            words_all = []
            for r in rects:
                r = fitz.Rect(r.x0-PAD, r.y0-PAD, r.x1+PAD, r.y1+PAD)
                words = page.get_text("words", clip=r)
                words_all.extend(words)

            if not words_all:
                return ""

            words_all.sort(key=lambda w: (round(w[1], 1), round(w[0], 1), w[5], w[6], w[7]))
            text_parts = []
            last_span = None
            for w in words_all:
                span = (w[0], w[1], w[2], w[3])
                if span != last_span:
                    text_parts.append(w[4])
                last_span = span
            return " ".join(text_parts).strip()
        except Exception as e:
            logging.warning("Highlight text extraction failed: %s", e)
            return ""

    # ---------- IRT utilities and reply filtering ----------
    def _get_irt_xref(self, annot):
        if hasattr(annot, "get_irt_xref"):
            try:
                return annot.get_irt_xref()
            except Exception:
                return None
        return None

    def _is_reply_text(self, annot) -> bool:
        try:
            subtype = (annot.type[1] or "").lower()
        except Exception:
            return False
        if subtype != "text":
            return False
        return self._get_irt_xref(annot) is not None

    # ---------- collect replies/popups and de-dup ----------
    def _collect_reply_comments_for_page(self, page) -> dict[int, list[str]]:
        parent_to_notes: dict[int, list[str]] = {}

        def _append_unique(bucket: list[str], txt: str):
            t = (txt or "").strip()
            if t and (not bucket or bucket[-1] != t) and t not in bucket:
                bucket.append(t)

        # pass 1: highlights with inline content
        a = page.first_annot
        while a:
            try:
                subtype = (a.type[1] or "").lower()
            except Exception:
                subtype = ""
            if any(k in subtype for k in ["highlight", "underline", "squiggly", "strike"]):
                c = (a.info or {}).get("content") or ""
                if c.strip():
                    parent_to_notes.setdefault(a.xref, [])
                    _append_unique(parent_to_notes[a.xref], c)
            a = a.next

        # pass 2: replies and popups via IRT
        a = page.first_annot
        while a:
            irt = self._get_irt_xref(a)
            try:
                subtype = (a.type[1] or "").lower()
            except Exception:
                subtype = ""
            info = a.info or {}

            if subtype == "text" and irt:
                parent_to_notes.setdefault(irt, [])
                _append_unique(parent_to_notes[irt], info.get("content") or "")

            try:
                pop = a.get_popup()
            except Exception:
                pop = None
            if pop and irt:
                parent_to_notes.setdefault(irt, [])
                _append_unique(parent_to_notes[irt], (pop.info or {}).get("content") or "")

            a = a.next

        return parent_to_notes

    # ---------- Ink clustering helpers ----------
    def _annot_creation_ts(self, annot) -> float:
        s = (annot.info or {}).get("creationDate") or (annot.info or {}).get("CreationDate") or ""
        try:
            s = s[2:] if s.startswith("D:") else s
            base = ''.join(ch for ch in s if ch.isdigit())
            if len(base) >= 14:
                dt = datetime(int(base[0:4]), int(base[4:6]), int(base[6:8]),
                              int(base[8:10]), int(base[10:12]), int(base[12:14]))
            elif len(base) >= 8:
                dt = datetime(int(base[0:4]), int(base[4:6]), int(base[6:8]))
            else:
                return 0.0
            return dt.timestamp()
        except Exception:
            return 0.0

    def _rect_union(self, r1: fitz.Rect, r2: fitz.Rect) -> fitz.Rect:
        return fitz.Rect(min(r1.x0, r2.x0), min(r1.y0, r2.y0), max(r1.x1, r2.x1), max(r1.y1, r2.y1))

    def _iou(self, a: fitz.Rect, b: fitz.Rect) -> float:
        inter = fitz.Rect(max(a.x0,b.x0), max(a.y0,b.y0), min(a.x1,b.x1), min(a.y1,b.y1))
        if inter.x1 <= inter.x0 or inter.y1 <= inter.y0:
            return 0.0
        ia = (inter.x1-inter.x0)*(inter.y1-inter.y0)
        ua = (a.x1-a.x0)*(a.y1-a.y0) + (b.x1-b.x0)*(b.y1-b.y0) - ia
        return ia/ua if ua>0 else 0.0

    def _contained(self, inner: fitz.Rect, outer: fitz.Rect, pad=1.0) -> bool:
        return (inner.x0 >= outer.x0 - pad and inner.y0 >= outer.y0 - pad and
                inner.x1 <= outer.x1 + pad and inner.y1 <= outer.y1 + pad)

    def _group_ink_annotations(self, page, time_window_s=8.0, iou_thresh=0.05):
        """
        Return list of clusters; each cluster is dict with:
          xrefs: [int], rect: fitz.Rect, ts_min: float, ts_max: float, members: [annot]
        Merge if IoU >= thresh OR one rect contains the other AND within time window.
        """
        inks = []
        a = page.first_annot
        while a:
            try:
                subtype = (a.type[1] or "").lower()
            except Exception:
                subtype = ""
            if "ink" in subtype:
                r = a.rect
                ts = self._annot_creation_ts(a)
                inks.append({"annot": a, "rect": r, "ts": ts})
            a = a.next

        used = [False]*len(inks)
        clusters = []
        for i, it in enumerate(inks):
            if used[i]:
                continue
            cur = {"xrefs": [it["annot"].xref], "rect": fitz.Rect(it["rect"]),
                   "ts_min": it["ts"], "ts_max": it["ts"], "members": [it["annot"]]}
            used[i] = True
            changed = True
            while changed:
                changed = False
                for j, jt in enumerate(inks):
                    if used[j]:
                        continue
                    # temporal gate
                    if cur["ts_min"] != 0.0 and jt["ts"] != 0.0:
                        if abs(jt["ts"] - cur["ts_max"]) > time_window_s and abs(jt["ts"] - cur["ts_min"]) > time_window_s:
                            continue
                    rj = jt["rect"]
                    riou = self._iou(cur["rect"], rj)
                    if riou >= iou_thresh or self._contained(rj, cur["rect"]) or self._contained(cur["rect"], rj):
                        cur["rect"] = self._rect_union(cur["rect"], rj)
                        cur["xrefs"].append(jt["annot"].xref)
                        cur["members"].append(jt["annot"])
                        cur["ts_min"] = min(cur["ts_min"], jt["ts"]) if cur["ts_min"] else jt["ts"]
                        cur["ts_max"] = max(cur["ts_max"], jt["ts"]) if cur["ts_max"] else jt["ts"]
                        used[j] = True
                        changed = True
            cur["xrefs"].sort()
            clusters.append(cur)
        return clusters

    # --- Ink Snapshot + OCR Helpers ---

    def _save_ink_snapshot(self, page, rect: fitz.Rect, notes_path: str,
                           pdf_path: str, page_number: int, label: str) -> str:
        """
        Saves a snapshot of a region as a PNG image. Used by cluster rendering.
        label: string suffix for filename uniqueness (e.g., 'CL_0')
        """
        media_dir = get_media_dir(notes_path)
        media_dir.mkdir(parents=True, exist_ok=True)

        pdf_stem = Path(pdf_path).stem
        filename = f"{pdf_stem}_p{page_number}_ink_{label}.png"
        out_path = media_dir / filename

        try:
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat, clip=rect)
            pix.save(out_path.as_posix())
            logging.debug("Saved ink snapshot: %s", out_path)
        except Exception:
            try:
                mat = fitz.Matrix(2, 2)
                pix = page.get_pixmap(matrix=mat)
                pix.save(out_path.as_posix())
                logging.debug("Saved ink snapshot (no clip): %s", out_path)
            except Exception as e:
                logging.error("Failed to save ink snapshot: %s", e)
                return ""

        rel_path = Path("notes_media") / filename
        return rel_path.as_posix()

    def _ocr_image_to_text(self, image_path: str) -> str:
        if not OCR_AVAILABLE:
            return ""
        try:
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img).strip()
            if len(text) < 3 or not any(ch.isalpha() for ch in text):
                return ""
            return text
        except Exception as e:
            logging.warning("OCR failed for %s: %s", image_path, e)
            return ""

    def scan_pdf(self, path: str, root_id: int, notes_path: str):
        logging.info("scan_pdf: start %s", path)
        if not DOCX_AVAILABLE:
            logging.warning("scan_pdf: python-docx not available, skipping %s", path)
            return
        if not os.path.exists(path):
            logging.warning("scan_pdf: file does not exist %s", path)
            return

        pdf_id = compute_pdf_id(path)
        if not pdf_id:
            logging.warning("scan_pdf: failed to compute PDF ID for %s", path)
            return

        try:
            mtime = os.path.getmtime(path)
        except FileNotFoundError:
            logging.warning("scan_pdf: file missing %s", path)
            return

        pdf_db_id = self.db.upsert_pdf(pdf_id, root_id, path, mtime)
        if pdf_db_id is None:
            logging.error("scan_pdf: DB upsert failed %s", path)
            return

        try:
            doc = fitz.open(path)
        except Exception as e:
            logging.exception("scan_pdf: fitz open failed %s: %s", path, e)
            return

        new_entries = []

        try:
            for page_index in range(len(doc)):
                page = doc[page_index]
                page_num = page_index + 1

                # gather replies mapped to their parent highlight
                reply_map = self._collect_reply_comments_for_page(page)

                # cluster inks for this page
                ink_clusters = self._group_ink_annotations(page)

                # iterate annotations for highlights and non-reply text notes
                try:
                    annot = page.first_annot
                except AttributeError:
                    annot = getattr(page, "firstAnnot", None)

                while annot:
                    info = getattr(annot, "info", {}) or {}
                    contents = (info.get("content") or "").strip()

                    try:
                        subtype_str = (annot.type[1] or "").lower()
                    except Exception:
                        subtype_str = ""

                    created_raw = info.get("creationDate") or info.get("CreationDate") or ""
                    created_fmt = parse_pdf_date(created_raw) or file_mtime_date(path)

                    kind = None
                    content_str = ""
                    snapshot_rel = ""

                    if any(k in subtype_str for k in ["highlight", "underline", "squiggly", "strike"]):
                        highlighted_text = self._get_highlighted_text(page, annot)
                        reply_notes = reply_map.get(annot.xref, [])

                        if highlighted_text and (contents or reply_notes):
                            note_text = "\n".join([t for t in [contents] + reply_notes if t.strip()])
                            content_str = f"Comment: {note_text}\nOn Text: \"{highlighted_text}\""
                            kind = "note"
                        elif highlighted_text:
                            content_str = highlighted_text
                            kind = "highlight"
                        elif contents or reply_notes:
                            content_str = "\n".join([t for t in [contents] + reply_notes if t.strip()])
                            kind = "note"

                    elif "text" in subtype_str:
                        # skip reply notes; already merged into parent
                        if self._is_reply_text(annot):
                            pass
                        else:
                            highlighted_text = self._get_highlighted_text(page, annot)
                            if highlighted_text and contents:
                                content_str = f"Comment: {contents}\nOn Text: \"{highlighted_text}\""
                                kind = "note"
                            elif contents:
                                content_str = contents
                                kind = "note"

                    elif "ink" in subtype_str:
                        # handled by clusters after the loop
                        pass

                    # Persist if valid
                    if kind:
                        xref = getattr(annot, "xref", None)
                        base = content_str or snapshot_rel or (contents or "")
                        chash = hashlib.sha256(base.encode("utf-8")).hexdigest()
                        annot_key = f"{page_index}:{subtype_str}:{xref}:{chash}"

                        if not self.db.annotation_exists(pdf_db_id, annot_key):
                            self.db.insert_annotation(pdf_db_id, annot_key, created_fmt, chash)
                            entry = self._format_entry(
                                pdf_path=path,
                                page_number=page_num,
                                created_date=created_fmt,
                                content=content_str,
                                kind=kind,
                                snapshot_rel=snapshot_rel,
                            )
                            new_entries.append(entry)

                    try:
                        annot = annot.next
                    except AttributeError:
                        annot = getattr(annot, "next", None)

                # After the while-loop, emit one entry per ink cluster
                for ci, cluster in enumerate(ink_clusters):
                    rect = cluster["rect"]
                    snapshot_rel = self._save_ink_snapshot(
                        page, rect, notes_path, path, page_num, label=f"CL_{ci}"
                    )

                    ocr_text = ""
                    if snapshot_rel:
                        media_dir = get_media_dir(notes_path)
                        snapshot_abs = media_dir / Path(snapshot_rel).name
                        ocr_text = self._ocr_image_to_text(snapshot_abs.as_posix())

                    group_key = ",".join(str(x) for x in cluster["xrefs"])
                    # stable content hash for cluster
                    chash = hashlib.sha256((ocr_text + (snapshot_rel or "") + group_key).encode("utf-8")).hexdigest()
                    annot_key = f"{page_index}:ink_cluster:{group_key}:{chash}"

                    # cluster creation date: earliest stroke if available
                    ts_min = cluster.get("ts_min") or 0.0
                    created_fmt = datetime.fromtimestamp(ts_min).strftime("%d-%b-%y") if ts_min else file_mtime_date(path)

                    if not self.db.annotation_exists(pdf_db_id, annot_key):
                        self.db.insert_annotation(pdf_db_id, annot_key, created_fmt, chash)
                        entry = self._format_entry(
                            pdf_path=path,
                            page_number=page_num,
                            created_date=created_fmt,
                            content=ocr_text,
                            kind="ink",
                            snapshot_rel=snapshot_rel,
                        )
                        new_entries.append(entry)

        except Exception:
            logging.exception("scan_pdf: error processing %s", path)

        doc.close()

        if new_entries:
            try:
                self._append_entries_grouped(notes_path, path, new_entries)
            except Exception:
                logging.exception("_append_entries_grouped FAILED for %s", path)

        logging.info("scan_pdf: finished %s", path)

    def _format_entry(self, pdf_path: str, page_number: int, created_date: str,
                      content: str, kind: str, snapshot_rel: str = ""):
        return {
            "pdf_path": pdf_path,
            "page": page_number,
            "date": created_date,
            "kind": kind,
            "content": content or "",
            "snapshot_rel": snapshot_rel or "",
        }

    @staticmethod
    def _insert_paragraph_after(paragraph: Paragraph, text: str = "", style=None) -> Paragraph:
        new_p = OxmlElement("w:p")
        paragraph._element.addnext(new_p)
        new_para = Paragraph(new_p, paragraph._parent)
        if text:
            new_para.add_run(text)
        if style is not None:
            new_para.style = style
        return new_para

    @classmethod
    def _append_entry_after(cls, notes_path: str, anchor: Paragraph, entry: dict) -> Paragraph:
        date = entry["date"]
        page = entry["page"]
        kind = entry["kind"]
        content = entry["content"]
        snapshot_rel = entry["snapshot_rel"]

        anchor = cls._insert_paragraph_after(anchor, f"Date: {date}")
        anchor = cls._insert_paragraph_after(anchor, f"Page(s): {page}")

        if kind == "highlight":
            anchor = cls._insert_paragraph_after(anchor, f'Highlighted: "{content}"')

        elif kind == "note":
            for line in content.splitlines():
                anchor = cls._insert_paragraph_after(anchor, line)

        elif kind == "ink":
            if content:
                anchor = cls._insert_paragraph_after(anchor, f'Handwritten: "{content}"')
            else:
                anchor = cls._insert_paragraph_after(anchor, "Drawn annotation on this page (ink strokes)")
            if snapshot_rel:
                img_path = Path(notes_path).parent / snapshot_rel
                if img_path.is_file():
                    img_para = cls._insert_paragraph_after(anchor)
                    try:
                        run = img_para.add_run()
                        run.add_picture(str(img_path), width=Inches(2))
                        anchor = img_para
                    except Exception as e:
                        logging.warning("Failed to embed image %s: %s", img_path, e)
                        anchor = img_para

        anchor = cls._insert_paragraph_after(anchor, "")
        return anchor

    @classmethod
    def _append_entries_grouped(cls, notes_path: str, pdf_path: str, entries):
        os.makedirs(os.path.dirname(notes_path), exist_ok=True)
        pdf_name = Path(pdf_path).name
        if not DOCX_AVAILABLE:
            return

        with cls._GLOBAL_DOC_LOCK:
            try:
                if os.path.exists(notes_path):
                    doc = Document(notes_path)
                else:
                    doc = Document()
            except PermissionError:
                logging.warning("PermissionError opening doc %s. Skipping.", notes_path)
                return
            except Exception as e:
                logging.exception("Failed to open doc %s: %s", notes_path, e)
                return

            paragraphs = doc.paragraphs
            target_para = None
            heading_level = 2

            for p in paragraphs:
                if p.text == pdf_name and p.style and p.style.name.startswith("Heading"):
                    target_para = p
                    try:
                        if p.style.name.startswith("Heading "):
                            heading_level = int(p.style.name.split()[-1])
                    except Exception:
                        heading_level = 2
                    break

            if target_para is None:
                heading = doc.add_heading(pdf_name, level=heading_level)
                anchor = heading
                for entry in entries:
                    anchor = cls._append_entry_after(notes_path, anchor, entry)
            else:
                paras = doc.paragraphs
                try:
                    start_idx = paras.index(target_para)
                except ValueError:
                    start_idx = 0
                end_idx = len(paras) - 1
                for j in range(start_idx + 1, len(paras)):
                    p2 = paras[j]
                    if p2.style and p2.style.name.startswith("Heading"):
                        try:
                            lvl = int(p2.style.name.split()[-1]) if p2.style.name.startswith("Heading ") else 9
                        except Exception:
                            lvl = 9
                        if lvl <= heading_level:
                            end_idx = j - 1
                            break
                anchor = paras[end_idx]
                for entry in entries:
                    anchor = cls._append_entry_after(notes_path, anchor, entry)

            try:
                doc.save(notes_path)
            except PermissionError:
                logging.warning("PermissionError saving doc %s. Skipping.", notes_path)
            except Exception as e:
                logging.exception("FAILED to save doc %s: %s", notes_path, e)

# =========================
# Watchdog File System Handler
# =========================

class PDFEventHandler(FileSystemEventHandler):
    def __init__(self, db: Database, scanner: PDFScanner, get_root_for_path):
        super().__init__()
        self.db = db
        self.scanner = scanner
        self.get_root_for_path = get_root_for_path
        self._debounce = {}
        self._queue = queue.Queue()
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    def _should_handle(self, src_path: str) -> bool:
        if not is_pdf(src_path):
            return False
        if not os.path.exists(src_path):
            return False
        root = self.get_root_for_path(src_path)
        return root is not None

    def _enqueue_scan(self, path: str):
        now = time.time()
        last = self._debounce.get(path, 0.0)
        if now - last < SCAN_DEBOUNCE_SECONDS:
            self._debounce[path] = now
            return
        self._debounce[path] = now
        self._queue.put(path)

    def _worker(self):
        while True:
            path = self._queue.get()
            if path is None:
                break
            time.sleep(SCAN_DEBOUNCE_SECONDS)
            now = time.time()
            if (now - self._debounce.get(path, 0.0)) > SCAN_DEBOUNCE_SECONDS:
                continue
            root = self.get_root_for_path(path)
            if not root:
                continue
            root_id, root_path, notes_path = root
            try:
                self.scanner.scan_pdf(path, root_id, notes_path)
            except Exception:
                logging.exception("Unhandled exception scanning %s", path)

    def on_created(self, event):
        if not event.is_directory and self._should_handle(event.src_path):
            self._enqueue_scan(event.src_path)

    def on_modified(self, event):
        if not event.is_directory and self._should_handle(event.src_path):
            self._enqueue_scan(event.src_path)

    def on_moved(self, event):
        if not event.is_directory and self._should_handle(event.dest_path):
            self._enqueue_scan(event.dest_path)

# =========================
# Main Application GUI
# =========================

class NotesWatcherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Note Organizer")

        try:
            icon_path = resource_path("Note icon.ico")
            try:
                from PIL import Image, ImageTk as _ImageTk
                img = Image.open(icon_path)
                try:
                    img = img.resize((64, 64), Image.LANCZOS)
                except Exception:
                    pass
                tk_img = _ImageTk.PhotoImage(img)
                self.root.iconphoto(False, tk_img)
                self._icon_image = tk_img
            except Exception:
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

        self.db = Database(DB_PATH)
        self.scanner = PDFScanner(self.db)

        self.observer = Observer()
        self.handler = PDFEventHandler(self.db, self.scanner, self.get_root_for_path)

        self._build_ui()
        self._load_watched_folders()
        self._start_observer()

    def _build_ui(self):
        frm = ttk.Frame(self.root, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        lbl = ttk.Label(frm, text="Watched Folders (recursive):")
        lbl.grid(row=0, column=0, columnspan=5, sticky="w")

        self.tree = ttk.Treeview(frm, columns=("root", "notes"), show="headings", height=8)
        self.tree.heading("root", text="Folder Path")
        self.tree.heading("notes", text="Notes File Path (.docx)")
        self.tree.column("root", width=350, stretch=True)
        self.tree.column("notes", width=350, stretch=True)
        self.tree.grid(row=1, column=0, columnspan=5, sticky="nsew", pady=5)

        frm.rowconfigure(1, weight=1)
        for col in range(5):
            frm.columnconfigure(col, weight=1 if col == 0 else 0)

        btn_frame_left = ttk.Frame(frm)
        btn_frame_left.grid(row=2, column=0, sticky="w", pady=5)

        btn_add = ttk.Button(btn_frame_left, text="Add a Folder to Watch", command=self.add_folder)
        btn_add.pack(side="left")

        btn_rescan = ttk.Button(btn_frame_left, text="Rescan All PDFs", command=self.rescan_all)
        btn_rescan.pack(side="left", padx=(6, 0))

        btn_remove = ttk.Button(frm, text="Remove Selected Folder", command=self.remove_selected)
        btn_remove.grid(row=2, column=1, sticky="w", pady=5)

        btn_open_folder = ttk.Button(frm, text="Open Selected Folder", command=self.open_selected_folder)
        btn_open_folder.grid(row=2, column=2, sticky="w", pady=5)

        btn_open_notes = ttk.Button(frm, text="Open Selected Notes File", command=self.open_selected_notes)
        btn_open_notes.grid(row=2, column=3, sticky="w", pady=5)

        note = ttk.Label(
            frm,
            text=(
                "Watches PDFs under each folder.\n"
                "Writes a Word (.docx) notes file per folder with entries grouped by PDF, "
                "including page number, dates, text annotations, and embedded ink snapshots."
            ),
        )
        note.grid(row=3, column=0, columnspan=5, sticky="w", pady=5)

        self._tooltip = None
        self._tooltip_after_id = None
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", lambda e: self._hide_tooltip())

    def _on_tree_motion(self, event):
        if self._tooltip_after_id:
            try:
                self.root.after_cancel(self._tooltip_after_id)
            except Exception:
                pass
        self._tooltip_after_id = self.root.after(200, lambda: self._show_tooltip(event))

    def _show_tooltip(self, event):
        item = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not item or col not in ("#1", "#2"):
            self._hide_tooltip()
            return
        vals = self.tree.item(item, "values")
        if not vals:
            self._hide_tooltip()
            return
        idx = 0 if col == "#1" else 1
        text = vals[idx]
        if not text:
            self._hide_tooltip()
            return
        if self._tooltip:
            try:
                lbl = self._tooltip.children.get("!label")
                if lbl:
                    lbl.config(text=text)
                self._tooltip.geometry(f"+{event.x_root+20}+{event.y_root+10}")
            except Exception:
                pass
            return
        try:
            self._tooltip = tk.Toplevel(self.root)
            self._tooltip.wm_overrideredirect(True)
            self._tooltip.attributes("-topmost", True)
            lbl = ttk.Label(self._tooltip, text=text, background="#ffffe0", relief="solid", borderwidth=1)
            lbl.pack(ipadx=6, ipady=3)
            self._tooltip.geometry(f"+{event.x_root+20}+{event.y_root+10}")
        except Exception:
            self._tooltip = None

    def _hide_tooltip(self):
        if self._tooltip_after_id:
            try:
                self.root.after_cancel(self._tooltip_after_id)
            except Exception:
                pass
            self._tooltip_after_id = None
        if self._tooltip:
            try:
                self._tooltip.destroy()
            except Exception:
                pass
            self._tooltip = None

    def _load_watched_folders(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in self.db.get_watched_folders():
            _id, root_path, notes_path = row
            self.tree.insert("", "end", iid=str(_id), values=(root_path, notes_path))

    def _start_observer(self):
        if hasattr(self.observer, "_watches"):
            try:
                existing = list(self.observer._watches.values())
            except Exception:
                try:
                    existing = list(self.observer._watches)
                except Exception:
                    existing = []
            for watch in existing:
                try:
                    self.observer.unschedule(watch)
                except Exception:
                    pass

        for row in self.db.get_watched_folders():
            _id, root_path, notes_path = row
            if os.path.isdir(root_path):
                self.observer.schedule(self.handler, root_path, recursive=True)

        if not self.observer.is_alive():
            try:
                self.observer.start()
            except RuntimeError:
                self.observer = Observer()
                self._start_observer()

    def _restart_observer(self):
        self._start_observer()

    def _get_selected_values(self):
        sel = self.tree.selection()
        if not sel:
            return None
        iid = sel[0]
        vals = self.tree.item(iid, "values")
        if not vals:
            return None
        root_path, notes_path = vals
        return str(root_path), str(notes_path)

    def add_folder(self):
        logging.info("Button: add_folder clicked")
        folder = filedialog.askdirectory()
        if not folder:
            logging.warning("add_folder: No folder selected")
            return
        folder = str(Path(folder).resolve())
        root_name = Path(folder).name
        notes_filename = f"Notes on {root_name}.docx"
        notes_path = str(Path(folder, notes_filename))

        for _id, root_path, _ in self.db.get_watched_folders():
            if folder == str(Path(root_path).resolve()):
                messagebox.showinfo("Info", "Folder is already being watched.")
                return

        self.db.add_watched_folder(folder, notes_path)
        self._load_watched_folders()
        self._restart_observer()

        def on_scan_complete():
            messagebox.showinfo("Initial Scan", f"Initial scan completed for:\n{folder}")

        def initial_scan_worker():
            logging.info(f"Starting initial scan for {folder}")
            try:
                row = self.db.get_watched_folder_by_path(folder)
                if not row:
                    return
                _id, root_path, np = row
                if not os.path.isdir(root_path):
                    return
                for dirpath, _, filenames in os.walk(root_path):
                    for name in filenames:
                        path = os.path.join(dirpath, name)
                        if is_pdf(path):
                            try:
                                self.scanner.scan_pdf(path, _id, np)
                            except Exception:
                                logging.exception("Failed to scan PDF in initial_scan: %s", path)
            finally:
                logging.info(f"Initial scan complete for {folder}")
                self.root.after(0, on_scan_complete)

        threading.Thread(target=initial_scan_worker, daemon=True).start()

    def remove_selected(self):
        logging.info("Button: remove_selected clicked")
        sel = self.tree.selection()
        if not sel:
            logging.warning("remove_selected: No folder selected")
            return
        for iid in sel:
            vals = self.tree.item(iid, "values")
            if not vals:
                continue
            root_path = vals[0]
            self.db.remove_watched_folder(root_path)
        self._load_watched_folders()
        self._restart_observer()

    def rescan_all(self):
        logging.info("Button: rescan_all clicked")
        folders = self.db.get_watched_folders()
        if not folders:
            messagebox.showinfo("Info", "No watched folders.")
            return

        def on_rescan_complete():
            logging.info("Rescan all complete.")
            messagebox.showinfo("Rescan", "Rescan complete.")

        def rescan_worker():
            logging.info("Starting rescan all...")
            try:
                for _id, root_path, notes_path in folders:
                    logging.info("Rescan: scanning root_path=%s (id=%s)", root_path, _id)
                    if not os.path.isdir(root_path):
                        logging.warning("Rescan: root_path not a directory, skipping: %s", root_path)
                        continue

                    def _on_walk_error(err):
                        logging.exception("Rescan: os.walk error on %s", err)

                    for dirpath, _, filenames in os.walk(root_path, onerror=_on_walk_error):
                        logging.debug("Rescan: walking dir %s", dirpath)
                        for name in filenames:
                            path = os.path.join(dirpath, name)
                            if is_pdf(path):
                                try:
                                    logging.debug("Rescan: scheduling scan for %s", path)
                                    self.scanner.scan_pdf(path, _id, notes_path)
                                except Exception:
                                    logging.exception("Failed to scan PDF during rescan: %s", path)
            finally:
                self.root.after(0, on_rescan_complete)

        threading.Thread(target=rescan_worker, daemon=True).start()

    def open_selected_folder(self):
        sel = self._get_selected_values()
        if not sel:
            messagebox.showinfo("Info", "No folder selected.")
            return
        root_path, _ = sel
        if not os.path.isdir(root_path):
            messagebox.showinfo("Info", "Folder path does not exist on disk.")
            return
        try:
            os.startfile(root_path)
        except AttributeError:
            try:
                os.system(f'open "{root_path}"')
            except Exception:
                try:
                    os.system(f'xdg-open "{root_path}"')
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to open folder:\n{e}")

    def open_selected_notes(self):
        sel = self._get_selected_values()
        if not sel:
            messagebox.showinfo("Info", "No folder selected.")
            return
        _, notes_path = sel
        if not os.path.isfile(notes_path):
            messagebox.showinfo("Info", "Notes file not found yet for this folder. Add or modify a PDF to create it.")
            return
        try:
            os.startfile(notes_path)
        except AttributeError:
            try:
                os.system(f'open "{notes_path}"')
            except Exception:
                try:
                    os.system(f'xdg-open "{notes_path}"')
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to open notes file:\n{e}")

    def get_root_for_path(self, path: str):
        path = str(Path(path).resolve())
        candidates = []
        for row in self.db.get_watched_folders():
            _id, root_path, notes_path = row
            root_path_resolved = str(Path(root_path).resolve())
            if (
                path.lower().startswith(root_path_resolved.lower() + os.sep.lower())
                or path.lower() == root_path_resolved.lower()
            ):
                candidates.append((len(root_path_resolved), (_id, root_path_resolved, notes_path)))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def on_close(self):
        logging.info("Application closing...")
        try:
            if self.observer.is_alive():
                self.observer.stop()
                self.observer.join(timeout=2)
        except Exception as e:
            logging.error("Error stopping observer: %s", e)
        self.root.destroy()

# =========================
# Entry point
# =========================

def main():
    missing = []
    try:
        import fitz  # noqa
    except ImportError:
        missing.append("PyMuPDF (fitz)")
    try:
        from watchdog.observers import Observer  # noqa
    except ImportError:
        missing.append("watchdog")
    if not DOCX_AVAILABLE:
        missing.append("python-docx")

    if missing:
        msg = "Missing required dependencies: " + ", ".join(missing)
        msg_pip = "Install with: pip install pymupdf watchdog python-docx"
        print(f"Error: {msg}", file=sys.stderr)
        print(msg_pip, file=sys.stderr)
        if OCR_AVAILABLE is False:
            print("Optional: pip install pillow pytesseract (plus system Tesseract) for handwriting OCR.", file=sys.stderr)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Missing Dependencies", f"{msg}\n\n{msg_pip}")
        except Exception:
            pass
        return

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s",
        handlers=[logging.FileHandler("app_log.txt", mode='w')],
    )
    logging.info("Application starting...")

    root = tk.Tk()
    app = NotesWatcherApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()

if __name__ == "__main__":
    main()
