"""Local PDF page search sharing the note reader's query language and scope."""
import json
from pathlib import Path

from .search import compile_search, match_spans, normalize, positive_terms
from .search_index import read as indexed_pages
from .storage import DEFAULT_SEARCH_FIELDS, SEARCH_FIELDS, search_values

SCOPES = ("Notes", "PDFs", "All")
MAX_PDF_RESULTS = 2000
# Cached pages include both their extraction order and normalized index text.
# A revision change rebuilds either kind of stale cache on its next search.
PDF_SEARCH_REVISION = 2
OCCURRENCE_FIELDS = ("quote", "comment", "ocr", "context", "color")
MATCH_SOURCES = {"quote": "Match in highlighted text", "comment": "Match in typed note",
                 "ocr": "Match in handwriting transcription", "context": "Match in surrounding text",
                 "color": "Match in annotation color",
                 "pdf": "Match in PDF text"}


class SearchResults(list):
    def __init__(self, entries=(), warnings=()):
        super().__init__(entries)
        self.warnings = list(warnings)


def file_version(path):
    stat = Path(path).stat()
    return json.dumps([stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns,
                       PDF_SEARCH_REVISION])


def excerpt(text, query, mode, length=260):
    hits = hit_excerpts(text, query, mode, max_length=length)
    if hits:
        return hits[0]["snippet"]
    text = " ".join(text.split())
    return text[:length] + ("…" if len(text) > length else "")


def hit_excerpts(text, query, mode="All words", context=60, max_length=260):
    """Describe every positive-term occurrence using original text offsets.

    Overlapping terms (such as ``gold`` and ``gold imaging``) describe one
    occurrence. Nearby occurrences share a context excerpt, while each retains
    an index for navigation and counting. Excerpt windows are bounded; the
    occurrence list is never capped. A single match longer than the excerpt is
    explicitly marked as truncated, with its full text and offsets retained.
    """
    return _hit_excerpts(text, positive_terms(query, mode), context, max_length)


def _hit_excerpts(text, terms, context=60, max_length=260):
    if context < 0 or max_length < 1:
        raise ValueError("Use a nonnegative context and a positive excerpt length.")
    if not terms:
        return []
    spans = []
    for start, end in match_spans(text, terms):
        if spans and start < spans[-1][1]:
            spans[-1] = (spans[-1][0], max(end, spans[-1][1]))
        else:
            spans.append((start, end))

    groups, hits = [], []
    for start, end in spans:
        width = end - start
        # Favor the complete match, then share the remaining context between
        # its two sides. An unusually long phrase still has a bounded preview.
        before = min(context, max(0, (max_length - width) // 2))
        after = min(context, max(0, max_length - width - before))
        left, right = max(0, start - before), min(len(text), end + after)
        right = min(right, left + max_length)
        if groups and left <= groups[-1]["end"] and right - groups[-1]["start"] <= max_length:
            group = groups[-1]
            group["end"] = max(group["end"], right)
        else:
            group = {"start": left, "end": right, "hit_indices": []}
            groups.append(group)
        hit_index = len(hits)
        group["hit_indices"].append(hit_index)
        matched = text[start:end]
        value = normalize(matched)
        hits.append({"start": start, "end": end, "text": matched, "term": value,
                     "normalized_text": value, "before": text[max(0, start - 100):start],
                     "after": text[end:end + 100],
                     "terms": [term for term in terms if term in value],
                     "excerpt_index": len(groups) - 1})

    for group in groups:
        left, right = group["start"], group["end"]
        snippet = ("…" if left else "") + " ".join(text[left:right].split()) + ("…" if right < len(text) else "")
        for index in group["hit_indices"]:
            hit = hits[index]
            hit.update({"snippet": snippet, "snippet_start": left, "snippet_end": right,
                        "snippet_truncated": hit["start"] < left or hit["end"] > right})
    return hits


def _group_excerpts(hits):
    groups = []
    for index, hit in enumerate(hits):
        if hit["excerpt_index"] == len(groups):
            groups.append({"start": hit["snippet_start"], "end": hit["snippet_end"],
                           "text": hit["snippet"], "hit_indices": [], "truncated": False})
        group = groups[hit["excerpt_index"]]
        group["hit_indices"].append(index)
        group["truncated"] = group["truncated"] or hit["snippet_truncated"]
    return groups


def enrich_note_matches(entry, query, fields=None, mode="All words", *, terms=None):
    """Attach all positive occurrences without changing note match semantics.

    A Boolean expression can match solely through NOT or a missing branch of
    an OR expression. Such a result deliberately retains an empty occurrence
    list; result navigation still provides one stop for that note. Identical
    enabled quote/comment/OCR passages share occurrences, as they share one
    passage in Note view. Their original field identities remain attached.
    """
    selected = set(DEFAULT_SEARCH_FIELDS if fields is None else fields)
    values = search_values(entry)
    hits, excerpts = [], []
    passages = {}
    if query.strip():
        terms = positive_terms(query, mode) if terms is None else terms
        for field in OCCURRENCE_FIELDS:
            if field not in selected or field not in SEARCH_FIELDS:
                continue
            value = values.get(field, "")
            shared_passage = field in {"quote", "comment", "ocr"} and bool(value)
            if shared_passage and value in passages:
                for item in (*passages[value][0], *passages[value][1]):
                    item["fields"].append(field)
                    item["source_labels"].append(MATCH_SOURCES[field])
                continue
            field_hits = _hit_excerpts(value, terms)
            groups = _group_excerpts(field_hits)
            hit_offset, excerpt_offset = len(hits), len(excerpts)
            for hit in field_hits:
                hit.update(field=field, source_label=MATCH_SOURCES[field],
                           fields=[field], source_labels=[MATCH_SOURCES[field]],
                           excerpt_index=hit["excerpt_index"] + excerpt_offset)
            for group in groups:
                group.update(field=field, source_label=MATCH_SOURCES[field],
                             fields=[field], source_labels=[MATCH_SOURCES[field]],
                             hit_indices=[index + hit_offset for index in group["hit_indices"]])
            hits.extend(field_hits)
            excerpts.extend(groups)
            if shared_passage:
                passages[value] = (field_hits, groups)
    entry.update(search_hits=hits, match_count=len(hits), match_excerpts=excerpts)
    return entry


def _pdf_metadata(store, documents, check):
    """Reuse reviewed citations without opening any of the source PDFs."""
    metadata = {document["id"]: json.loads(document["metadata"]) for document in documents}
    ids = list(metadata)
    with store.connect() as db:
        for start in range(0, len(ids), 400):
            check()
            batch = ids[start:start + 400]
            rows = db.execute("SELECT document_id,payload FROM paper_citations WHERE document_id IN ("
                              + ",".join("?" for _ in batch) + ")", batch)
            for row in rows:
                citation = json.loads(row["payload"])
                details = metadata[row["document_id"]]
                details.update({key: value for key, value in citation.items() if key != "pages"})
                details["citation_pages"] = citation.get("pages", "")
                details["author"] = "; ".join(citation.get("authors", []))
    return metadata


def search_library(store, worker, scope="Notes", **options):
    if scope not in SCOPES:
        raise ValueError("Choose Notes, PDFs, or All.")
    progress = options.pop("progress", None)
    cancelled = options.get("cancelled") or (lambda: False)
    def check():
        if cancelled():
            raise InterruptedError("Search cancelled")
    check()
    from .research_tools import label_ids
    selected_labels = label_ids(store, options.pop("label_filter", "All papers"))
    query, mode = options.get("query", ""), options.get("match_mode", "All words")
    matcher = compile_search(query, mode)
    terms = positive_terms(query, mode)
    if options.get("fields") is None:
        options["fields"] = DEFAULT_SEARCH_FIELDS
    results = SearchResults(store.entries(**options) if scope != "PDFs" else ())
    if selected_labels is not None:
        results[:] = [entry for entry in results if entry["document_id"] in selected_labels]
    for entry in results:
        check()
        enrich_note_matches(entry, query, options["fields"], mode, terms=terms)
    if scope == "Notes":
        return results
    documents = store.search_documents(options.get("project_id"), options.get("document_id"))
    if selected_labels is not None:
        documents = [document for document in documents if document["id"] in selected_labels]
    metadata_by_id = _pdf_metadata(store, documents, check)
    browsing = not query.strip()
    seen, selected = set(), []
    primary_paths = {document["path"] for document in documents
                     if not metadata_by_id[document["id"]].get("managed_cloud_id")}
    for document in documents:
        check()
        metadata = metadata_by_id[document["id"]]
        path = document["path"]
        # Managed tablet notes reuse the primary article's printed pages. Search
        # that article once; standalone tablet documents are rendered on demand.
        # Stored paths are already canonical; resolving them again can open a
        # file handle even though catalog browsing needs no filesystem access.
        identity = (str(Path(path)).casefold(), document["digest"])
        if metadata.get("managed_cloud_id") and metadata.get("primary_path"):
            if metadata["primary_path"] in primary_paths:
                continue
        if identity in seen:
            continue
        seen.add(identity)
        selected.append(document)
    completed, pdf_count = 0, 0
    counts = {"cached": 0, "indexed": 0, "issues": 0}
    def report(detail=""):
        check()
        if progress:
            progress({"phase": "Loading PDFs" if browsing else "Searching PDFs", "unit": "PDFs",
                      "current": completed, "total": len(selected), "detail": detail, **counts})
    report()
    for document in selected:
        check()
        metadata = metadata_by_id[document["id"]]
        path = document["path"]
        report(Path(path).name)
        managed = bool(metadata.get("managed_cloud_id"))
        entry = {"document_id": document["id"], "kind": "pdf", "path": path,
                 "rect": [0, 0, 0, 0], "metadata": metadata,
                 "logical_paper_id": document.get("logical_paper_id") if managed else None,
                 "result_paper_id": document.get("logical_paper_id"),
                 "logical_paper_title": metadata.get("title") or document.get("logical_paper_title")
                     or (document.get("paper_source") or {}).get("title", ""),
                 "source_digest": document["digest"], "missing": document["missing"]}
        if browsing:
            # Empty-query browsing is a catalog operation. Do not stat, fetch,
            # render or index a PDF until the reader requests its contents.
            results.append({**entry, "key": "pdf-document", "pdf_document": True,
                            "page": 1, "page_count": None, "pdf_label": "",
                            "quote": "", "context": ""})
            completed += 1
            report(Path(path).name)
            continue
        finished_document = True
        try:
            physical = worker.materialize(store.path, document.get("logical_paper_id") or path) if managed else path
            version = file_version(physical)
            indexed = indexed_pages(store, document["id"], document["digest"], version, query, mode)
            if indexed is None:
                pages = store.cached_pdf_pages(document["id"], document["digest"], version)
                if pages is None:
                    if hasattr(type(worker), "text_pages_cancellable"):
                        pages = worker.text_pages_cancellable(physical, None if managed else document["digest"], cancelled)
                    else:
                        pages = worker.text_pages(physical, None if managed else document["digest"])
                    check()
                    if version != file_version(physical):
                        raise OSError("PDF changed while indexing; sync it and search again.")
                    counts["indexed"] += 1
                else:
                    counts["cached"] += 1
                store.cache_pdf_pages(document["id"], document["digest"], version, pages)
                indexed = indexed_pages(store, document["id"], document["digest"], version, query, mode)
                if indexed is None:
                    raise ValueError("Library changed during indexing. Search again.")
            else:
                counts["cached"] += 1
            pages, page_count, has_text = indexed
            if page_count and not has_text:
                counts["issues"] += 1
                results.warnings.append(f"{Path(path).name}: No searchable text layer. Scanned pages need OCR before PDF text search.")
                continue
            for page in pages:
                check()
                if not page["text"].strip():
                    continue
                if not matcher([normalize(page["text"])]):
                    continue
                hits = _hit_excerpts(page["text"], terms)
                for hit in hits:
                    hit.update(field="pdf", source_label=MATCH_SOURCES["pdf"])
                excerpts = _group_excerpts(hits)
                for group in excerpts:
                    group.update(field="pdf", source_label=MATCH_SOURCES["pdf"])
                results.append({**entry, "key": f"pdf-page:{page['page']}", "page": page["page"],
                                "page_count": page_count, "pdf_label": page["pdf_label"],
                                "quote": hits[0]["snippet"] if hits else excerpt(page["text"], query, mode),
                                "context": page["text"], "search_hits": hits,
                                "match_count": len(hits), "match_excerpts": excerpts})
                pdf_count += 1
                if pdf_count >= MAX_PDF_RESULTS:
                    finished_document = False
                    results.warnings.append("Showing the first 2,000 PDF page matches. Narrow your search to see more.")
                    return results
        except InterruptedError:
            finished_document = False
            raise
        except Exception as exc:
            counts["issues"] += 1
            results.warnings.append(f"{Path(path).name}: {exc}")
        finally:
            if finished_document and not cancelled():
                completed += 1
                report(Path(path).name)
    check()
    return results
