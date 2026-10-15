"""Paper identification and stable ordering for the reader's mixed results."""
from pathlib import Path
from html import unescape

from .exporting import paper_title
from .pages import page_description


def paper_identity(entry):
    identity = entry.get("result_paper_id") or entry.get("logical_paper_id")
    if identity:
        return ("paper", str(identity))
    return ("file", str(Path(entry["path"])).casefold())


def result_title(entry):
    metadata = entry.get("metadata", {})
    if entry.get("logical_paper_title"):
        metadata = {**metadata, "title": entry["logical_paper_title"]}
    return paper_title(entry["path"], metadata)


def title_source(entry):
    raw = entry.get("logical_paper_title") or entry.get("metadata", {}).get("title", "")
    if raw and unescape(raw).strip() == result_title(entry):
        # Catalog rows can copy PDF metadata into logical_paper_title without
        # recording whether a citation was reviewed. Do not invent provenance.
        return "Saved paper title or PDF metadata" if entry.get("logical_paper_title") else "PDF metadata"
    return "Filename fallback; save a title in Citation details"


def paper_labels(entries):
    titles, sources = {}, {}
    for entry in entries:
        identity = paper_identity(entry)
        titles.setdefault(identity, result_title(entry))
        sources.setdefault(identity, Path(entry["path"]))
    duplicates = {}
    for identity, title in titles.items():
        duplicates.setdefault(title.casefold(), []).append(identity)
    labels = {identity: title + (" · " + sources[identity].name if len(duplicates[title.casefold()]) > 1 else "")
              for identity, title in titles.items()}
    collisions = {}
    for identity, label in labels.items():
        collisions.setdefault(label.casefold(), []).append(identity)
    for identities in collisions.values():
        if len(identities) > 1:
            for identity in identities:
                labels[identity] += " · " + str(sources[identity].parent)
    return labels


def result_excerpt(entry):
    if entry.get("pdf_document"):
        return "Unavailable PDF" if entry.get("missing") else "PDF document"
    hits = entry.get("search_hits") or ()
    if hits:
        hit = hits[0]
        text = hit.get("snippet") or hit.get("text", "")
        if hit.get("field") not in {None, "quote", "comment", "ocr", "pdf"}:
            return f"{hit.get('source_label', 'Search match')}: {text}"
        if text:
            return text
    return entry.get("comment") or entry.get("quote") or entry.get("ocr") or "Drawing with page context"


def result_type(entry):
    """Return the label used for both the Type column and its ordering."""
    kind = entry["kind"]
    return {"pdf": "PDF", "highlight": "Highlight", "drawing": "Drawing", "text": "Note"}.get(kind, kind.capitalize())


def result_tooltip(entry):
    metadata = entry.get("metadata", {})
    author = metadata.get("author") or metadata.get("authors", "")
    if isinstance(author, (list, tuple)):
        author = "; ".join(str(value) for value in author)
    citation = " · ".join(str(value) for value in (author, metadata.get("year")) if value)
    lines = [result_title(entry)]
    if citation:
        lines.append(citation)
    lines.append("Title source: " + title_source(entry))
    lines.append("File: " + Path(entry["path"]).name)
    lines.append("PDF document" if entry.get("pdf_document") else page_description(entry))
    if "match_count" in entry and not entry.get("pdf_document"):
        count = entry["match_count"]
        location = "on this page" if entry.get("kind") == "pdf" else "in this result"
        lines.append(f"{count} search occurrence{'' if count == 1 else 's'} {location}")
    if not entry.get("pdf_document"):
        lines.extend(["", result_excerpt(entry)])
    if entry.get("missing"):
        lines.extend(["", "Source file is unavailable."])
    lines.extend(["", "Location: " + entry["path"]])
    return "\n".join(lines)


def ordered_rows(entries, rows, column="paper", descending=False):
    """Sort numeric row IDs without changing the entry/selection mapping."""
    labels = paper_labels(entries)
    def paper_key(row):
        entry = entries[int(row)]
        identity = paper_identity(entry)
        return (labels[identity].casefold(), identity)

    def page_key(row):
        entry = entries[int(row)]
        rect = entry.get("rect", [0, 0, 0, 0])
        return (entry.get("page", 1), tuple(entry.get("order") or (rect[1], rect[0])),
                entry["path"].casefold(), entry["key"])

    def source_type(row):
        return int(entries[int(row)].get("kind") == "pdf")

    result = sorted(rows, key=page_key)
    result.sort(key=source_type)
    result.sort(key=paper_key)
    if column == "kind":
        result.sort(key=lambda row: result_type(entries[int(row)]).casefold(), reverse=descending)
    elif column == "page":
        result.sort(key=lambda row: entries[int(row)].get("page", 1), reverse=descending)
    else:
        result.sort(key=paper_key, reverse=descending)
    return result
