"""Synthetic long-text dissertation coverage probe, not a user-library benchmark."""
import json
from pathlib import Path
import time
from unittest.mock import Mock

from run_preflight import HERE
import pymupdf as fitz
from note_organizer.pdf_worker import _text_pages
from note_organizer.storage import Store, digest_file
from note_organizer.research_search import search_library
from note_organizer.sorting.core_logic import get_basic_document_details

folder = HERE / "long-dissertation-fixture"
folder.mkdir(exist_ok=True)
path = folder / "synthetic-dissertation-140-pages.pdf"
line = "Background alpha beta gamma delta epsilon theta iota kappa lambda observations."
with fitz.open() as pdf:
    for index in range(140):
        page = pdf.new_page()
        page.insert_text((50, 50), "\n".join([line] * 60), fontsize=8)
        if index == 0:
            page.insert_text((50, 800), "A synthetic dissertation for application evaluation")
        if index == 139:
            page.insert_text((50, 800), "terminalpreflightomega")
    pdf.save(path)
before = digest_file(path)
pages = _text_pages(path)
details = get_basic_document_details(path)
store = Store(folder / "synthetic.sqlite3")
project = store.add_project(folder)
store.save_scan(project, path, before, "probe", "probe", details, [])
worker = Mock()
worker.text_pages.side_effect = _text_pages
start = time.monotonic()
result = search_library(store, worker, "PDFs", query="terminalpreflightomega", include_images=False)
first_seconds = time.monotonic() - start
start = time.monotonic()
cached = search_library(store, worker, "PDFs", query="terminalpreflightomega", include_images=False)
summary = {
    "description": "One synthetic text-heavy dissertation; no scanned scientific layout or handwriting",
    "page_count": len(pages),
    "extracted_characters": sum(len(page["text"]) for page in pages),
    "characters_before_last_page": sum(len(page["text"]) for page in pages[:-1]),
    "classification": details["document_type"],
    "terminal_token_pages": [row["page"] for row in result],
    "warnings": result.warnings,
    "first_index_and_search_seconds": round(first_seconds, 3),
    "cached_search_seconds": round(time.monotonic() - start, 3),
    "extraction_calls_for_two_queries": worker.text_pages.call_count,
    "source_unchanged": before == digest_file(path),
}
(HERE / "long-dissertation-results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
