"""Run isolated, synthetic, non-GUI Notable preliminary checks.

This evaluation writes only below this newly created research directory. It
does not open the user's library, start the GUI, or connect to a cloud account.
"""
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCRATCH = HERE / "scratch"
SCRATCH.mkdir(exist_ok=True)
os.environ.update(TEMP=str(SCRATCH), TMP=str(SCRATCH), PYTHONDONTWRITEBYTECODE="1")
sys.path.insert(0, str(ROOT))
import tempfile
tempfile.tempdir = str(SCRATCH)

GROUPS = [
    ["tests.test_research_features.ResearchTests"],
    ["tests.test_search_accuracy"],
    ["tests.test_supplement_integration.SupplementIntegrationTests"],
    ["tests.test_cloud_outbox"],
    ["tests.test_remarkable"],
    ["tests.test_combined_pdf"],
    ["tests.test_sorting_citations_and_recovery.CitationTests"],
]


def synthetic_probe():
    from unittest.mock import Mock
    import pymupdf as fitz
    from note_organizer.pdf_worker import _text_pages
    from note_organizer.storage import Store, digest_file
    from note_organizer.research_search import search_library
    from note_organizer.sorting.core_logic import get_basic_document_details, build_proposed_filename
    from note_organizer.citations import normalize_record, ris, bibtex

    folder = HERE / "synthetic-fixtures"
    folder.mkdir(exist_ok=True)
    path = folder / "dissertation.pdf"
    with fitz.open() as pdf:
        for text in ["A synthetic nanoparticle dissertation\nJane Example\n2025\nA dissertation submitted to Example University.",
                     "Catalysis observations on the second page."]:
            page = pdf.new_page()
            page.insert_text((50, 70), text)
        pdf.set_metadata({"title": "A synthetic nanoparticle dissertation", "author": "Jane Example"})
        pdf.save(path)
    details = get_basic_document_details(path)
    record = normalize_record({"title": details["title"], "authors": ["Example, Jane"],
                               "year": "2025", "document_type": "thesis_dissertation",
                               "university": "Example University", "thesisType": "PhD thesis"})
    store = Store(folder / "synthetic.sqlite3")
    project = store.add_project(folder)
    store.save_scan(project, path, digest_file(path), "probe", "probe", details, [])
    worker = Mock()
    worker.text_pages.side_effect = _text_pages
    outcomes = {}
    for query in ["nanoparticle", "catalysis", "nanoparticle AND catalysis", '"synthetic nanoparticle"',
                  "nanoparticle NOT catalysis", "nanoparticle OR catalysis"]:
        result = search_library(store, worker, "PDFs", query=query, include_images=False)
        outcomes[query] = {"pages": [row["page"] for row in result], "warnings": result.warnings}
    # Rasterize the first page to produce a readable screenshot PDF without a text layer.
    scan_path = folder / "screenshot.pdf"
    with fitz.open(path) as source, fitz.open() as scan:
        page = scan.new_page(width=source[0].rect.width, height=source[0].rect.height)
        page.insert_image(page.rect, pixmap=source[0].get_pixmap())
        scan.save(scan_path)
    store.save_scan(project, scan_path, digest_file(scan_path), "probe", "probe", {}, [])
    scan_id = store.document_at(project, scan_path)["id"]
    scan_result = search_library(store, worker, "PDFs", query="nanoparticle", document_id=scan_id, include_images=False)
    return {
        "fixture_kind": "Synthetic two-page thesis plus screenshot PDF; no personal documents",
        "dissertation_classification": details.get("document_type"),
        "dissertation_proposed_filename": build_proposed_filename(details, path.suffix),
        "citation_fields_retained": sorted(record),
        "university_retained": "university" in record,
        "thesis_type_retained": "thesisType" in record,
        "RIS_type_line": ris([record]).splitlines()[0],
        "BibTeX_type_line": bibtex([record]).splitlines()[0],
        "PDF_search": outcomes,
        "screenshot_search": {"count": len(scan_result), "warnings": scan_result.warnings},
        "original_source_unchanged_by_search": path.exists() and digest_file(path) == store.document_at(project, path)["digest"],
    }


def main():
    summary = {"date": datetime.now().isoformat(), "python": sys.version,
               "root": str(ROOT), "write_root": str(HERE), "groups": []}
    for number, modules in enumerate(GROUPS, 1):
        command = [sys.executable, "-B", "-m", "unittest", *modules, "-v"]
        start = time.monotonic()
        result = subprocess.run(command, cwd=ROOT, env=os.environ.copy(), text=True,
                                encoding="utf-8", errors="replace", stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=240)
        log = HERE / f"group-{number}.log"
        log.write_text(result.stdout, encoding="utf-8")
        summary["groups"].append({"command": command, "exit_code": result.returncode,
                                   "seconds": round(time.monotonic() - start, 2), "log": log.name})
        print(f"Group {number}: {', '.join(modules)} -> exit {result.returncode}; "
              f"{summary['groups'][-1]['seconds']} seconds", flush=True)
        print("\n".join(result.stdout.splitlines()[-4:]), flush=True)
    summary["synthetic_probe"] = synthetic_probe()
    (HERE / "results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary["synthetic_probe"], indent=2), flush=True)
    return int(any(row["exit_code"] for row in summary["groups"]))


if __name__ == "__main__":
    raise SystemExit(main())
