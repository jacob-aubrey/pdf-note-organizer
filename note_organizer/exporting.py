"""Atomic, reproducible Word exports with preservation of external edits."""
import base64
from datetime import datetime
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
import tempfile
from itertools import groupby

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.shared import Inches, Pt, RGBColor
from PIL import Image

from .storage import digest_file, entry_sort_key


def file_uri(path, page):
    return Path(path).resolve().as_uri() + f"#page={page}"


def hyperlink(paragraph, label, url):
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True))
    run = OxmlElement("w:r")
    props = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "245A81")
    props.append(color)
    run.append(props)
    text = OxmlElement("w:t")
    text.text = label
    run.append(text)
    link.append(run)
    paragraph._p.append(link)


def _build_detailed_notebook(title, entries):
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = section.bottom_margin = Inches(.7)
    section.left_margin = section.right_margin = Inches(.8)
    for name in ("Normal", "Title", "Heading 1", "Heading 2"):
        doc.styles[name].font.name = "Calibri"
        doc.styles[name].font.color.rgb = RGBColor(0, 0, 0)
    normal = doc.styles["Normal"]
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    doc.styles["Title"].font.size = Pt(24)
    doc.styles["Heading 1"].font.size = Pt(16)
    doc.styles["Heading 2"].font.size = Pt(12)
    doc.add_paragraph(title, "Title")
    doc.add_paragraph("Annotations collected from your PDFs, with source links and visual context. "
                      "This notebook is regenerated when the source annotations change. "
                      "Use an editable copy for your own writing.")
    doc.add_paragraph(f"Generated {datetime.now():%d %B %Y at %H:%M}. {len(entries)} annotations.")
    if not entries:
        doc.add_paragraph("No annotations have been extracted yet.")
    previous = None
    for e in entries:
        if e["path"] != previous:
            previous = e["path"]
            title = e.get("metadata", {}).get("title") or Path(previous).stem
            doc.add_heading(title, 1)
            p = doc.add_paragraph()
            hyperlink(p, Path(previous).name, file_uri(previous, 1))
            doc.add_paragraph(str(Path(previous).parent), style="Caption")
            meta = e.get("metadata", {})
            if meta.get("author"):
                doc.add_paragraph(f"Author: {meta['author']}")
            if meta.get("doi"):
                p = doc.add_paragraph("DOI: ")
                hyperlink(p, meta["doi"], "https://doi.org/" + meta["doi"])
            if e.get("missing"):
                doc.add_paragraph("Source unavailable. Previously extracted notes are retained.")
            for warning in meta.get("warnings", []):
                doc.add_paragraph(warning)
        label = f"Page {e['label']}"
        if str(e["page"]) != e["label"]:
            label += f" (PDF page {e['page']})"
        p = doc.add_paragraph(style="Heading 2")
        hyperlink(p, label, file_uri(e["path"], e["page"]))
        p.add_run(f"  |  {e['kind'].capitalize()}" + (f"  |  {e['color']}" if e.get("color") else ""))
        created = re.match(r"(?:D:)?(\d{4})(\d{2})(\d{2})", e.get("created", ""))
        if created:
            doc.add_paragraph("Annotation date: " + "-".join(created.groups()), style="Caption")
        if e.get("quote"):
            p = doc.add_paragraph()
            p.add_run("Highlighted text: ").bold = True
            p.add_run(e["quote"])
        if e.get("comment"):
            p = doc.add_paragraph()
            p.add_run("Comment: ").bold = True
            p.add_run(e["comment"])
        if e.get("image") and (e["kind"] not in {"highlight", "underline", "strikeout", "squiggly"} or not e.get("quote")):
            raw = base64.b64decode(e["image"])
            with Image.open(BytesIO(raw)) as img:
                width, height = img.size
            # Keep page crops readable without forcing tall images beyond a page.
            inches = min(6.7, max(1.5, width / 144), 7.2 * width / max(height, 1))
            p = doc.add_paragraph()
            p.add_run().add_picture(BytesIO(raw), width=Inches(inches))
            doc.add_paragraph("Original page with annotations and surrounding context", style="Caption")
        if e.get("ocr"):
            p = doc.add_paragraph()
            p.add_run("Suggested transcription (verify against image): ").bold = True
            p.add_run(e["ocr"])
    return doc


def clean_text(value):
    """PDF strings can contain control characters that Word's XML rejects."""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", "\ufffd", str(value or ""))


def ordered_entries(entries):
    return sorted(entries, key=entry_sort_key)


def paper_title(path, metadata):
    title = metadata.get("title", "").strip()
    # Publishers sometimes set the title to a typesetting job ID or page range.
    if not title or re.search(r"\.indd$|\d+\.\.\d+$|^[A-Z]{1,6}[_-]\d{4,}", title):
        return Path(path).stem.replace("_", " ")
    return title


def build_notebook(title, entries, documents=None, layout="Reading"):
    # Preserve the stored source verbatim; sanitize only the XML representation.
    entries = [{**e, **{key: clean_text(e.get(key, "")) for key in
                ("quote", "comment", "ocr", "label", "created", "color")},
                "metadata": {k: clean_text(v) if isinstance(v, str) else v
                             for k, v in e.get("metadata", {}).items()}}
               for e in ordered_entries(entries)]
    title = clean_text(title)
    if layout == "Detailed":
        return _build_detailed_notebook(title, entries)
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = section.bottom_margin = Inches(.75)
    section.left_margin = section.right_margin = Inches(.85)
    styles = doc.styles
    for name in ("Normal", "Quote"):
        styles[name].font.name = "Georgia"
        styles[name].font.size = Pt(11)
        styles[name].font.color.rgb = RGBColor.from_string("20252A")
        styles[name].paragraph_format.line_spacing = 1.15
        styles[name].paragraph_format.space_after = Pt(8)
        styles[name].paragraph_format.widow_control = True
    styles["Quote"].paragraph_format.left_indent = Inches(.18)
    styles["Quote"].paragraph_format.right_indent = Inches(.1)
    styles["Quote"].font.italic = False
    for name, size in (("Title", 25), ("Heading 1", 17), ("Heading 2", 11)):
        styles[name].font.name = "Segoe UI"
        styles[name].font.size = Pt(size)
        styles[name].font.color.rgb = RGBColor(0, 0, 0)
        styles[name].paragraph_format.space_before = Pt(16 if name == "Heading 1" else 9)
        styles[name].paragraph_format.space_after = Pt(7)
    styles["Caption"].font.name = "Segoe UI"
    styles["Caption"].font.size = Pt(9)
    styles["Caption"].font.color.rgb = RGBColor.from_string("59636D")
    doc.add_paragraph(title, "Title")
    if not entries:
        doc.add_paragraph("No notes yet.")
        return doc
    doc.add_paragraph("Selected passages and reading notes", "Subtitle")
    for path, paper_iter in groupby(entries, key=lambda e: e["path"]):
        paper = list(paper_iter)
        meta = paper[0].get("metadata", {})
        doc.add_heading(paper_title(path, meta), 1)
        source = doc.add_paragraph(style="Caption")
        if meta.get("author"):
            source.add_run(meta["author"] + "  ·  ")
        hyperlink(source, Path(path).name, file_uri(path, 1))
        if meta.get("doi"):
            source.add_run("  ·  ")
            hyperlink(source, "DOI", "https://doi.org/" + meta["doi"])
        if paper[0].get("missing"):
            doc.add_paragraph("Source unavailable. Previously saved notes are retained.", "Caption")
        for page, page_iter in groupby(paper, key=lambda e: e["page"]):
            page_entries = list(page_iter)
            label = page_entries[0]["label"] or str(page)
            heading = doc.add_paragraph(style="Heading 2")
            hyperlink(heading, f"Page {label}" + (f" (PDF {page})" if label != str(page) else ""), file_uri(path, page))
            shown_images = set()
            for e in page_entries:
                if e["quote"]:
                    quote = doc.add_paragraph(e["quote"], "Quote")
                    # Keep the source passage with its attached comment where possible.
                    quote.paragraph_format.keep_with_next = bool(e["comment"])
                if e["comment"]:
                    p = doc.add_paragraph()
                    p.add_run("Note: ").bold = True
                    p.add_run(e["comment"])
                image = e.get("image")
                needs_image = e["kind"] not in {"highlight", "underline", "strikeout", "squiggly"} or not e["quote"]
                if image and needs_image and image not in shown_images:
                    shown_images.add(image)
                    raw = base64.b64decode(image)
                    with Image.open(BytesIO(raw)) as img:
                        width, height = img.size
                    inches = min(6.8, max(1.5, width/144), 7.3*width/max(height, 1))
                    doc.add_paragraph().add_run().add_picture(BytesIO(raw), width=Inches(inches))
                if e["ocr"]:
                    doc.add_paragraph("Transcription to check: " + e["ocr"], "Caption")
    return doc


def export_notebook(path, title, entries, expected_hash="", layout="Reading"):
    """Save beside the target then replace. Preserve all pre-existing edited files."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    original_hash = digest_file(path) if path.exists() else None
    fd, temp = tempfile.mkstemp(prefix=".pdf-notes-", suffix=".docx", dir=path.parent)
    os.close(fd)
    backup = None
    try:
        build_notebook(title, entries, layout=layout).save(temp)
        # Verify the zip is readable before replacing a working notebook.
        Document(temp)
        if original_hash is not None and original_hash != expected_hash:
            backup_dir = path.parent / "Notebook backups"
            backup_dir.mkdir(exist_ok=True)
            # A locked Word file may be retried repeatedly: preserve one copy per revision.
            backup = backup_dir / f"{path.stem}.{original_hash}.docx"
            if not backup.exists():
                shutil.copy2(path, backup)
            if digest_file(backup) != original_hash:
                raise OSError("Notebook changed while preserving edits; retry when Word is closed.")
        now_hash = digest_file(path) if path.exists() else None
        if now_hash != original_hash:
            raise OSError("Notebook changed during export; retry when Word is closed.")
        os.replace(temp, path)
        return digest_file(path), str(backup) if backup else ""
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
