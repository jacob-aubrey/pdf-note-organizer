"""Isolated audit probes; no library/cloud/device access."""
from pathlib import Path
import json
import sys
import tempfile
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from note_organizer.sorting.presentation_extraction import extract_presentation
from note_organizer.sorting.core_logic import get_basic_document_details
from note_organizer.sorting import core_logic
from note_organizer.sorting.metadata_lookup import DOIResolution
from tests.test_sorting_presentation_extraction import _write_pptx
from note_organizer.zotero_worker import Worker


def main():
    results = {}
    with tempfile.TemporaryDirectory(prefix="shared-audit-", dir=Path(__file__).resolve().parent) as temporary:
        folder = Path(temporary)
        source = folder / "partial.pptx"
        _write_pptx(source, ["A complete lecture\nAuthors: Jane Smith\nYear: 2025", "Second slide"],
                    title="A complete lecture", author="Jane Smith")
        with zipfile.ZipFile(source) as archive:
            payload = {name: archive.read(name) for name in archive.namelist()
                       if name != "ppt/slides/slide2.xml"}
        with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in payload.items():
                archive.writestr(name, data)
        extraction = extract_presentation(source)
        details = get_basic_document_details(source)
        worker = Worker.__new__(Worker)
        worker.config = {}
        plugin_details = worker._proposal(source, {"title": "Reviewed lecture", "date": "2025",
            "creators": [{"creatorType": "author", "name": "Jane Smith"}]})["details"]
        results["partial_pptx"] = {
            "declared_slides": extraction.slide_count,
            "warnings": extraction.warnings,
            "requires_manual_review": extraction.requires_manual_review,
            "proposal_needs_review": details["needs_review"],
            "proposal_review_reasons": details["review_reasons"],
            "plugin_proposal_needs_review": plugin_details["needs_review"],
            "plugin_proposal_review_reasons": plugin_details["review_reasons"],
        }
    extraction = core_logic.DocumentExtraction(
        text="Computed tomography imaging of gold nanoparticles in rabbits\n"
             "Authors: Jane Rabbit\nYear: 2026\nAbstract\nA rabbit experiment.\n"
             "References\nA Rat. Computed tomography imaging of gold nanoparticles in rats. "
             "DOI: 10.1234/rats.2025",
        metadata={"title": "Computed tomography imaging of gold nanoparticles in rabbits"},
        document_format="PDF")
    reference = DOIResolution(doi="10.1234/rats.2025", provider="fixture", evidence_label="Fixture",
        title="Computed tomography imaging of gold nanoparticles in rats", authors=("Alice Rat",),
        journal="Journal of Rats", year="2025", document_type="journal_article")
    with patch.object(core_logic, "extract_document", return_value=extraction), \
            patch.object(core_logic, "resolve_doi", return_value=reference):
        proposal = core_logic.get_document_details("rabbits.pdf", "", allow_cloud_ai=False)
    results["reference_doi_false_match"] = {
        "document_title": extraction.metadata["title"],
        "reference_title": reference.title,
        "match_score": core_logic._title_match_score(extraction.metadata["title"], reference.title),
        "proposal_title": proposal["title"], "proposal_author": proposal["primary_creator"],
        "evidence_label": proposal["evidence_label"], "needs_review": proposal["needs_review"],
        "candidate_dois": core_logic._document_doi_candidates(extraction),
    }
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
