"""Editable bibliographic records kept separately from replaceable PDF scans."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .sorting.metadata_lookup import normalize_doi, resolve_doi

FIELDS = (("title", "Title"), ("authors", "Authors (separate with semicolons)"),
          ("year", "Year"), ("journal", "Journal / venue"), ("volume", "Volume"),
          ("issue", "Issue"), ("pages", "Pages / article number"), ("doi", "DOI"), ("url", "URL"))


def clean(value):
    return " ".join(str(value or "").split())


def normalize_record(record):
    result = {key: clean(record.get(key)) for key, _ in FIELDS if key != "authors"}
    authors = record.get("authors") or record.get("creators") or record.get("author") or []
    if isinstance(authors, str):
        authors = authors.split(";")
    result["authors"] = [clean(author) for author in authors if clean(author)]
    doi = record.get("doi") or (record.get("identifier") or {}).get("doi", "")
    result["doi"] = normalize_doi(doi)
    result["journal"] = result["journal"] or clean(record.get("venue_or_publisher"))
    result["url"] = result["url"] or clean((record.get("identifier") or {}).get("url"))
    if doi and not result["doi"]:
        raise ValueError("Enter a valid DOI, its doi.org URL, or leave DOI blank.")
    return result


def citation_for(store, document_id):
    documents = store.search_documents(document_id=document_id, whole_paper=True)
    selected = next((row for row in documents if row["id"] == document_id), None)
    if selected is None:
        raise ValueError("This paper is no longer in the library.")
    with store.connect() as db:
        ordered = [selected] + [row for row in documents if row["id"] != document_id]
        for document in ordered:
            saved = db.execute("SELECT payload FROM paper_citations WHERE document_id=?", (document["id"],)).fetchone()
            if saved:
                return json.loads(saved[0])
        metadata = json.loads(selected["metadata"])
        # PDF /Pages is a page count, not a citation page range.
        metadata.pop("pages", None)
        # Filing already collected reviewed citation details; reuse them locally.
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inbox_jobs'").fetchone():
            job = db.execute("SELECT details FROM inbox_jobs WHERE path=? ORDER BY created_at DESC LIMIT 1",
                             (selected["path"],)).fetchone()
            if job:
                metadata.update({key: value for key, value in json.loads(job[0]).items() if value})
    record = normalize_record(metadata)
    record["title"] = record["title"] or selected.get("logical_paper_title") or Path(selected["path"]).stem
    return record


def save_citation(store, document_id, record):
    record = normalize_record(record)
    if not record["title"]:
        raise ValueError("Enter a paper title before saving its citation.")
    documents = store.search_documents(document_id=document_id, whole_paper=True)
    if not documents:
        raise ValueError("This paper is no longer in the library.")
    with store.connect() as db:
        db.executemany("INSERT OR REPLACE INTO paper_citations VALUES(?,?)",
                       [(row["id"], json.dumps(record, ensure_ascii=False)) for row in documents])
        db.executemany("UPDATE projects SET dirty=1 WHERE id=?",
                       [(project_id,) for project_id in {row["project_id"] for row in documents}])
        from .supplement_library import bind_pending
        bind_pending(db)
    return record


def lookup_citation(doi):
    doi = normalize_doi(doi)
    if not doi:
        raise ValueError("Enter a valid DOI first.")
    resolution = resolve_doi(doi)
    if resolution is None:
        raise ValueError("No citation metadata was found for this DOI. You can enter the details manually.")
    return normalize_record(resolution.as_document_details())


def citation_text(record):
    record = normalize_record(record)
    parts = ["; ".join(record["authors"]), f"({record['year']})" if record["year"] else "",
             record["title"], record["journal"]]
    locator = record["volume"] + (f"({record['issue']})" if record["issue"] else "")
    parts.extend([locator, record["pages"], f"https://doi.org/{record['doi']}" if record["doi"] else record["url"]])
    return ". ".join(part.rstrip(".") for part in parts if part) + "."


def ris(records):
    output = []
    for record in records:
        row = normalize_record(record)
        lines = ["TY  - JOUR" if row["journal"] else "TY  - GEN"]
        lines.extend("AU  - " + author for author in row["authors"])
        for key, tag in (("title", "TI"), ("year", "PY"), ("journal", "JO"), ("volume", "VL"),
                         ("issue", "IS"), ("pages", "SP"), ("doi", "DO"), ("url", "UR")):
            if row[key]:
                if key == "pages" and re.fullmatch(r"\d+\s*[-–]\s*\d+", row[key]):
                    first, last = re.split(r"\s*[-–]\s*", row[key])
                    lines.extend(["SP  - " + first, "EP  - " + last])
                else:
                    lines.append(f"{tag}  - {row[key]}")
        output.append("\n".join(lines + ["ER  - ", ""]))
    return "\n".join(output)


def tex(value):
    replacements = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "&": r"\&",
                    "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(replacements.get(char, char) for char in value)


def bibtex(records):
    output, used = [], set()
    for record in records:
        row = normalize_record(record)
        key = "notable" + hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:12]
        base, suffix = key, 2
        while key in used:
            key, suffix = f"{base}_{suffix}", suffix + 1
        used.add(key)
        fields = {"author": " and ".join("{" + tex(author) + "}" if " and " in author.casefold() else tex(author)
                                         for author in row["authors"])}
        fields.update({("number" if name == "issue" else name): tex(value) for name, value in row.items()
                       if name != "authors" and value})
        lines = [f"@{'article' if row['journal'] else 'misc'}{{{key},"]
        lines.extend(f"  {name} = {{{value}}}," for name, value in fields.items() if value)
        output.append("\n".join(lines + ["}"]))
    return "\n\n".join(output) + "\n"


def export_citations(store, document_ids, target):
    target = Path(target)
    if target.suffix.lower() not in {".ris", ".bib"}:
        raise ValueError("Choose a .ris or .bib filename for citations.")
    records, seen = [], set()
    for document_id in document_ids:
        related = store.search_documents(document_id=document_id, whole_paper=True)
        identity = frozenset(row["id"] for row in related)
        if not identity or identity in seen:
            continue
        seen.add(identity)
        records.append(citation_for(store, document_id))
    if not records:
        raise ValueError("There are no papers to export in this selection.")
    content = ris(records) if target.suffix.lower() == ".ris" else bibtex(records)
    descriptor, temporary = tempfile.mkstemp(prefix=".notable-citations-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return len(records)
