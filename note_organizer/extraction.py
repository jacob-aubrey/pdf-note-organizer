"""Extract complete snapshots without modifying the source PDF."""
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import fitz

from .storage import digest_file


GRAPHICS = {"ink", "line", "polyline", "polygon", "square", "circle", "stamp", "caret"}
MARKUP = {"highlight", "underline", "squiggly", "strikeout"}
EXTRACTION_REVISION = 2


def scan_fingerprint(settings):
    return json.dumps({**{k: v for k, v in settings.items() if k != "notebook_style"},
                       "extractor_revision": EXTRACTION_REVISION}, sort_keys=True)


def signature(path):
    s = Path(path).stat()
    return f"{s.st_size}:{s.st_mtime_ns}"


def annotation_key(annot):
    return (annot.info or {}).get("id") or f"xref-{annot.xref}"


def grouping_rect(annot):
    # Ink vertices avoid large PDF appearance padding around each letter.
    if annot.type[1].lower() == "ink" and annot.vertices:
        points = [p for stroke in annot.vertices for p in stroke]
        if points:
            xs, ys = zip(*points)
            return fitz.Rect(min(xs), min(ys), max(xs) + .1, max(ys) + .1)
    return fitz.Rect(annot.rect)


def group_graphics(annotations, mode="Nearby blocks", gap=24):
    """Connected nearby strokes, including adjacent letters and arrow endpoints.

    Compare actual member rectangles, not the expanding cluster bounding box:
    empty space within a large arrow cannot swallow an unrelated note.
    """
    if not annotations:
        return []
    if mode == "Whole page":
        return [annotations]
    rects = [grouping_rect(a) for a in annotations]
    parents = list(range(len(rects)))

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    for i, a in enumerate(rects):
        for j in range(i):
            b = rects[j]
            dx = max(0, a.x0 - b.x1, b.x0 - a.x1)
            dy = max(0, a.y0 - b.y1, b.y0 - a.y1)
            # A smaller vertical reach in line mode keeps adjacent lines separate.
            vertical_gap = gap if mode == "Nearby blocks" else min(5, gap / 3)
            if dx <= gap and dy <= vertical_gap:
                parents[root(i)] = root(j)
    groups = {}
    for i, annot in enumerate(annotations):
        groups.setdefault(root(i), []).append(annot)
    return sorted(groups.values(), key=lambda g: (min(a.rect.y0 for a in g), min(a.rect.x0 for a in g)))


def padded_rect(page, rect, padding):
    bounds = page.rect * page.derotation_matrix
    return fitz.Rect(rect.x0-padding, rect.y0-padding, rect.x1+padding, rect.y1+padding) & bounds


def context_rect(page, rect, padding, lines):
    crop = padded_rect(page, rect, padding)
    initial = fitz.Rect(crop)
    for line in lines:
        # Expand whole intersecting lines so a crop does not end halfway through a word.
        if line.intersects(initial):
            crop |= line
    return padded_rect(page, crop, 5)


def snapshot(page, rect):
    # Annotation coordinates are unrotated; rendering clips are in rotated page space.
    clip = rect * page.rotation_matrix
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip, annots=True)
    return base64.b64encode(pix.tobytes("png")).decode("ascii")


def ink_only(page, members, rect):
    """Isolate strokes for optional OCR; context image always uses the original PDF."""
    with fitz.open() as canvas:
        bounds = page.rect * page.derotation_matrix
        blank = canvas.new_page(width=bounds.width, height=bounds.height)
        for a in members:
            if a.type[1].lower() != "ink":
                continue
            ink = blank.add_ink_annot(a.vertices)
            ink.set_colors(stroke=a.colors.get("stroke") or (0, 0, 0))
            ink.set_border(width=(a.border or {}).get("width", 1) or 1)
            ink.update()
        return snapshot(blank, rect)


def ocr_image(image):
    executable = shutil.which("tesseract")
    if not executable:
        return "", "OCR unavailable: install Tesseract or leave transcription off."
    try:
        with tempfile.TemporaryDirectory(prefix="pdf-notes-ocr-") as folder:
            path = Path(folder) / "ink.png"
            path.write_bytes(base64.b64decode(image))
            result = subprocess.run([executable, str(path), "stdout", "--psm", "6"],
                                    capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:
                return "", "OCR failed; the original annotation image is retained."
            return result.stdout.decode("utf-8", errors="replace").strip(), ""
    except (OSError, subprocess.TimeoutExpired):
        return "", "OCR failed or timed out; the original annotation image is retained."


def highlighted_words(page, annot):
    verts = annot.vertices or []
    rects = [fitz.Quad(verts[i:i+4]).rect for i in range(0, len(verts)-3, 4)] or [annot.rect]
    words = page.get_text("words")
    selected, seen = [], set()
    for rect in rects:
        for w in sorted(words, key=lambda w: (w[5], w[6], w[7])):
            box = fitz.Rect(w[:4])
            area = box.get_area()
            if area and (box & rect).get_area() / area >= .35:
                identity = tuple(w[:8])
                if identity not in seen:
                    selected.append(w)
                    seen.add(identity)
    return selected


def highlighted_text(page, annot):
    return " ".join(w[4] for w in highlighted_words(page, annot))


def reading_order(page_words, selected_words, rect):
    if selected_words:
        return list(min(tuple(w[5:8]) for w in selected_words))
    if page_words:
        # Anchor drawings / sticky notes to the nearest actual text, keeping column flow.
        def distance(w):
            box = fitz.Rect(w[:4])
            dx = max(0, box.x0 - rect.x1, rect.x0 - box.x1)
            dy = max(0, box.y0 - rect.y1, rect.y0 - box.y1)
            return (dx*dx + dy*dy, w[5], w[6], w[7])
        return list(min(page_words, key=distance)[5:8])
    return [rect.y0, rect.x0, 0]


def color_label(annot):
    rgb = annot.colors.get("stroke") or annot.colors.get("fill")
    if not rgb or len(rgb) != 3:
        return ""
    palette = {"Yellow": (1, 1, 0), "Green": (0, 1, 0), "Blue": (0, .5, 1),
               "Pink": (1, .4, .7), "Red": (1, 0, 0), "Orange": (1, .6, 0), "Black": (0, 0, 0)}
    return min(palette, key=lambda c: sum((a-b)**2 for a, b in zip(rgb, palette[c])))


def extract(path, settings, cancelled=None):
    before = signature(path)
    digest = digest_file(path)
    entries, warnings = [], []
    with fitz.open(path) as doc:
        if doc.needs_pass:
            raise ValueError("Password-protected PDF: save an unlocked copy for annotation extraction.")
        metadata = dict(doc.metadata or {})
        metadata["pages"] = len(doc)
        # DOI is extracted only when visibly present; authors/year are never guessed.
        first_text = "\n".join(doc[i].get_text() for i in range(min(2, len(doc))))
        doi = re.search(r"\b10\.\d{4,9}/[^\s<>\"]+", first_text, re.IGNORECASE)
        if doi:
            metadata["doi"] = doi.group().rstrip(".,;)")
        for index, page in enumerate(doc):
            if cancelled and cancelled():
                raise InterruptedError("Scan stopped")
            annotations = list(page.annots() or [])
            if not annotations:
                continue
            lines = [fitz.Rect(line["bbox"]) for block in page.get_text("dict")["blocks"]
                     for line in block.get("lines", [])]
            page_words = page.get_text("words")
            by_xref = {a.xref: a for a in annotations}
            replies = {}
            consumed = set()
            for a in annotations:
                parent = a.irt_xref
                visited = {a.xref}
                while parent in by_xref and parent not in visited:
                    visited.add(parent)
                    next_parent = by_xref[parent].irt_xref
                    if not next_parent:
                        break
                    parent = next_parent
                if parent in by_xref and parent != a.xref and a.type[1].lower() in {"text", "freetext"}:
                    replies.setdefault(parent, []).append((a.info or {}).get("content", ""))
                    consumed.add(a.xref)
            graphics = [a for a in annotations if a.type[1].lower() in GRAPHICS]
            groups = group_graphics(graphics, settings.get("grouping", "Nearby blocks"), settings.get("gap", 24))
            handled_graphics = {a.xref for a in graphics}
            units = [(g, "drawing") for g in groups]
            units += [([a], a.type[1].lower()) for a in annotations if a.xref not in handled_graphics | consumed]
            for members, kind in units:
                if cancelled and cancelled():
                    raise InterruptedError("Scan stopped")
                a = members[0]
                if kind in {"popup", "link"}:
                    continue
                rect = fitz.Rect(a.rect)
                for member in members[1:]:
                    rect |= member.rect
                comments = []
                for member in members:
                    for value in [(member.info or {}).get("content", "")] + replies.get(member.xref, []):
                        value = value.strip()
                        if value and value not in comments:
                            comments.append(value)
                selected_words = highlighted_words(page, a) if kind in MARKUP else []
                quote = " ".join(w[4] for w in selected_words)
                crop = context_rect(page, rect, settings.get("context_padding", 36), lines)
                if kind == "drawing" and settings.get("grouping") == "Whole page":
                    crop = page.rect * page.derotation_matrix
                entry = {"key": f"{index}:" + "+".join(sorted(annotation_key(m) for m in members)),
                         "page": index + 1, "label": page.get_label() or str(index+1),
                         "kind": kind, "rect": list(rect), "crop": list(crop), "quote": quote,
                         "order": reading_order(page_words, selected_words, rect),
                         "comment": "\n".join(comments), "color": color_label(a),
                         "created": (a.info or {}).get("creationDate", ""),
                         "modified": (a.info or {}).get("modDate", ""), "ocr": "", "image": "",
                         "context": page.get_text("text", clip=crop, sort=True).strip()}
                # Every annotation retains a context image, including image-only highlighted pages.
                entry["image"] = snapshot(page, crop)
                if kind == "drawing" and settings.get("ocr") and any(m.type[1].lower() == "ink" for m in members):
                    entry["ocr"], warning = ocr_image(ink_only(page, members, padded_rect(page, rect, 8)))
                    if warning and warning not in warnings:
                        warnings.append(warning)
                if kind in MARKUP and not quote:
                    warning = f"Page {index+1}: highlighted text unavailable; a context image was retained."
                    if warning not in warnings:
                        warnings.append(warning)
                entries.append(entry)
    if signature(path) != before or digest_file(path) != digest:
        raise OSError("PDF changed during extraction; waiting for a stable saved copy.")
    metadata["warnings"] = warnings
    return digest, before, metadata, entries
