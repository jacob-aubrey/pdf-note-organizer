"""Local PDF page search sharing the note reader's query language and scope."""
import json
from pathlib import Path

from .search import compile_search, normalize, tokenize

SCOPES = ("Notes", "PDFs", "All")
MAX_PDF_RESULTS = 2000


class SearchResults(list):
    def __init__(self, entries=(), warnings=()):
        super().__init__(entries)
        self.warnings = list(warnings)


def file_version(path):
    stat = Path(path).stat()
    return json.dumps([stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns])


def excerpt(text, query, mode, length=260):
    text = " ".join(text.split())
    terms = [normalize(query)] if mode == "Exact phrase" else [word for kind, word in tokenize(query) if kind == "TERM"]
    lower = text.casefold()
    positions = [lower.find(term) for term in terms if term and term in lower]
    start = max(0, min(positions, default=0) - 70)
    return ("…" if start else "") + text[start:start+length] + ("…" if len(text) > start+length else "")


def search_library(store, worker, scope="Notes", **options):
    if scope not in SCOPES:
        raise ValueError("Choose Notes, PDFs, or All.")
    cancelled = options.get("cancelled") or (lambda: False)
    def check():
        if cancelled():
            raise InterruptedError("Search cancelled")
    check()
    query, mode = options.get("query", ""), options.get("match_mode", "All words")
    matcher = compile_search(query, mode)
    results = SearchResults(store.entries(**options) if scope != "PDFs" else ())
    # Browsing Notes/All with an empty query never indexes every paper.
    if scope == "Notes" or not query.strip():
        return results
    documents = store.search_documents(options.get("project_id"), options.get("document_id"))
    seen, pdf_count = set(), 0
    for document in documents:
        check()
        metadata = json.loads(document["metadata"])
        path = document["path"]
        # Managed tablet notes reuse the primary article's printed pages. Search
        # that article once; standalone tablet documents are rendered on demand.
        identity = (str(Path(path).resolve()).casefold(), document["digest"])
        if metadata.get("managed_cloud_id") and metadata.get("primary_path"):
            if any(other["path"] == metadata["primary_path"] and not
                   json.loads(other["metadata"]).get("managed_cloud_id") for other in documents):
                continue
        if identity in seen:
            continue
        seen.add(identity)
        try:
            managed = bool(metadata.get("managed_cloud_id"))
            physical = worker.materialize(store.path, document.get("logical_paper_id") or path) if managed else path
            version = file_version(physical)
            pages = store.cached_pdf_pages(document["id"], document["digest"], version)
            if pages is None:
                pages = worker.text_pages(physical, None if managed else document["digest"])
                check()
                if version != file_version(physical):
                    raise OSError("PDF changed while indexing; sync it and search again.")
                store.cache_pdf_pages(document["id"], document["digest"], version, pages)
            if pages and not any(page["text"].strip() for page in pages):
                results.warnings.append(f"{Path(path).name}: No searchable text layer. Scanned pages need OCR before PDF text search.")
                continue
            for page in pages:
                check()
                if not page["text"].strip():
                    continue
                if not matcher([normalize(page["text"])]):
                    continue
                results.append({"document_id": document["id"], "key": f"pdf-page:{page['page']}",
                                "kind": "pdf", "path": path, "page": page["page"],
                                "page_count": len(pages), "pdf_label": page["pdf_label"],
                                "rect": [0, 0, 0, 0], "metadata": metadata,
                                "quote": excerpt(page["text"], query, mode), "context": page["text"],
                                "logical_paper_id": document.get("logical_paper_id") if managed else None,
                                "source_digest": document["digest"], "missing": document["missing"]})
                pdf_count += 1
                if pdf_count >= MAX_PDF_RESULTS:
                    results.warnings.append("Showing the first 2,000 PDF page matches. Narrow your search to see more.")
                    return results
        except InterruptedError:
            raise
        except Exception as exc:
            results.warnings.append(f"{Path(path).name}: {exc}")
    return results
