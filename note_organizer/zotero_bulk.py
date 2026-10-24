"""Content-based library intake and exception-only review policy.

The source tree is read-only. Zotero owns stored copies and citation lookup;
the existing bridge remains the only code that applies tablet annotations.
"""
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import time

from .remarkable_cloud import atomic_write
from .zotero_pilot import PilotError, TransportInterrupted
from .zotero_review import fingerprint


EXTENSIONS = {".pdf", ".docx", ".pptx"}


def digest_file(path, algorithm="sha256"):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def observed_digest(path, cache):
    """Memoize observations only; actions still rehash before changing a file."""
    path = Path(path)
    stat = path.stat()
    signature = (str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    if signature not in cache:
        cache[signature] = digest_file(path)
    return cache[signature]


def title_key(value):
    return " ".join(re.findall(r"\w+", str(value).casefold()))


def doi_key(value):
    from .sorting.metadata_lookup import normalize_doi
    return normalize_doi(value).casefold()


def inspect_document(path, *, evidence=False):
    from .sorting.core_logic import extract_document, _basic_details_from_extraction, _document_doi_candidates
    extraction = extract_document(path)
    if path.suffix.lower() == ".pdf":
        if not extraction.page_or_section_count:
            raise PilotError("The PDF has no readable pages or needs a password.")
    details = _basic_details_from_extraction(path, extraction)
    result = {"title": details["title"], "document_type": details["document_type"],
              "dois": _document_doi_candidates(extraction),
              "supplement": details.get("is_supplementary_material", False)}
    if evidence:
        result["evidence"] = extraction.text[:24000]
    return result


def library_index(catalog, documents=None, *, cancelled=lambda: False, cache=None):
    """Hash each local attachment once per operation, including managed baselines."""
    by_digest, by_key = defaultdict(list), {}
    cache = {} if cache is None else cache
    for row in catalog["attachments"]:
        if cancelled():
            raise PilotError("Stopped. Your files were retained.")
        path = Path(row["path"])
        try:
            digest = observed_digest(path, cache)
        except OSError:
            continue  # Unavailable Zotero files cannot establish an exact match.
        value = {**row, "digest": digest}
        by_digest[digest].append(value)
        by_key[row["data"]["key"]] = value
    for link in (documents or {}).values():
        key = link.get("view_key") or link.get("source_key")
        if key in by_key and link.get("baseline"):
            values = by_digest[link["baseline"]]
            if not any(r["data"]["key"] == key for r in values):
                values.append(by_key[key])
    return by_digest, by_key


def candidate_references(info, catalog):
    """Suggest a possible version/reference collision, never use it as PDF identity."""
    title = title_key(info.get("title", ""))
    dois = {doi_key(v) for v in info.get("dois", []) if doi_key(v)}
    return [p for p in catalog["parents"].values() if
            (doi_key(p.get("DOI", "")) in dois if doi_key(p.get("DOI", "")) else False)
            or (len(title) >= 18 and title_key(p.get("title", "")) == title)]


class BulkLibrary:
    def __init__(self, worker):
        self.worker = worker
        self.path = worker.directory / "bulk-library.json"

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else None

    def save(self, plan):
        atomic_write(self.path, json.dumps(plan, ensure_ascii=False).encode())

    def scan(self, root, collection, lookup=True):
        worker = self.worker
        worker.stop.clear()
        root = Path(root).resolve(strict=True)
        if not root.is_dir():
            raise PilotError("Choose a literature folder.")
        client = worker.zotero()
        try:
            collections = client.collections()
            if collection not in {r["key"] for r in collections}:
                raise PilotError("Choose a current personal Zotero collection.")
            catalog = client.review_action("catalog")
            data_directory = catalog.get("data_directory")
            if data_directory:
                data = Path(data_directory).resolve()
                if root.is_relative_to(data) or data.is_relative_to(root):
                    raise PilotError("Choose your literature folder, outside Zotero's data directory.")
            indexed, _ = library_index(catalog, worker.state.read("documents", {}), cancelled=worker.stop.is_set, cache=worker.file_digests)
            grouped, failures = {}, []
            paths = []
            worker.progress('Finding documents in your Windows folder…')
            for directory, folders, names in os.walk(root, followlinks=False):
                folders[:] = [name for name in sorted(folders) if not Path(directory, name).is_symlink()
                              and not Path(directory, name).is_junction()]
                for name in sorted(names):
                    if worker.stop.is_set():
                        raise PilotError("Scan stopped. No library changes were made.")
                    path = Path(directory, name)
                    if path.suffix.lower() not in EXTENSIONS or name.startswith("~$"):
                        continue
                    if path.is_symlink() or not path.resolve().is_relative_to(root):
                        continue
                    paths.append(path)
            for number, path in enumerate(paths, 1):
                if worker.stop.is_set():
                    raise PilotError('Scan stopped. No library changes were made.')
                worker.progress(f'Scanning file {number} of {len(paths)}: {path.name}')
                try:
                    before = path.stat()
                    digest = digest_file(path)
                    if (before.st_size, before.st_mtime_ns) != (path.stat().st_size, path.stat().st_mtime_ns):
                        raise PilotError("The file changed during the scan.")
                    if digest in grouped:
                        grouped[digest]["copies"].append(str(path))
                        continue
                    row = {"id": digest[:24], "digest": digest, "path": str(path), "copies": [str(path)],
                           "issues": [], "status": "pending", "existing": "", "parent": ""}
                    grouped[digest] = row
                    try:
                        row["info"] = inspect_document(path)
                    except Exception:
                        row["info"] = {"title": path.stem, "dois": []}
                        row["issues"].append("The file could not be read completely; inspect it before import.")
                    matches = indexed.get(digest, [])
                    if len(matches) == 1:
                        row["existing"] = matches[0]["data"]["key"]
                        row["parent"] = matches[0]["data"].get("parentItem", "")
                    elif matches:
                        row["issues"].append("Identical content belongs to multiple Zotero attachments; choose which reference to keep.")
                    else:
                        candidates = candidate_references(row["info"], catalog)
                        if candidates:
                            row["issues"].append("A possibly matching reference already exists; its PDF or edition needs checking.")
                            row["candidates"] = [{"key": p["key"], "title": p.get("title", "")} for p in candidates]
                    if not row["existing"] and (row["info"].get("supplement") or re.search(r"(?:^|[_ -])(?:si|supporting[ _-]?information|supplement(?:ary)?)(?:$|[_ -])", path.stem, re.I)):
                        row["issues"].append("Supporting information needs its main reference identified.")
                except (OSError, PilotError) as error:
                    failures.append({"path": str(path), "reason": str(error)})
            # Different bytes with the same filename or document title can be
            # editions or annotated copies. Preserve both and ask, not overwrite.
            names = defaultdict(set)
            for row in grouped.values():
                for key in ("name:" + title_key(Path(row["path"]).stem), "title:" + title_key(row["info"].get("title", ""))):
                    if len(key) >= 18:
                        names[key].add(row["digest"])
            collisions = set().union(*(values for values in names.values() if len(values) > 1)) if names else set()
            for digest in collisions:
                grouped[digest]["issues"].append("Another source file has the same name or title but different content; check the versions.")
            plan = {"id": fingerprint([str(root), collection, time.time_ns()]), "root": str(root),
                    "collection": collection, "lookup": bool(lookup), "rows": list(grouped.values()), "failures": failures}
            self.save(plan)
            worker.collections = collections
            return worker.status()
        finally:
            client.close()

    def apply(self, plan_id):
        worker = self.worker
        plan = self.read()
        if not plan or plan["id"] != plan_id:
            raise PilotError("The folder scan changed. Review its current summary first.")
        worker.stop.clear()
        client = worker.zotero()
        try:
            catalog = client.review_action("catalog")
            indexed, _ = library_index(catalog, worker.state.read("documents", {}), cancelled=worker.stop.is_set)
            for number, row in enumerate(plan["rows"], 1):
                if worker.stop.is_set():
                    break
                if row["issues"] or row["status"] == "complete":
                    continue
                worker.progress(f'Importing / reusing document {number} of {len(plan["rows"])}…')
                path = Path(row["path"])
                try:
                    if not path.resolve(strict=True).is_relative_to(Path(plan["root"])) or digest_file(path) != row["digest"]:
                        raise PilotError("The source changed after scanning. Scan again before importing it.")
                    matches = indexed.get(row["digest"], [])
                    if len(matches) > 1:
                        raise PilotError("An identical PDF now belongs to several Zotero attachments.")
                    existing = matches[0] if matches else None
                    if row["existing"] and (not existing or existing["data"]["key"] != row["existing"]):
                        raise PilotError("The matching Zotero attachment changed after scanning.")
                    if existing:
                        parent_key = existing['data'].get('parentItem')
                        parent = catalog['parents'].get(parent_key, {})
                        if plan['collection'] in parent.get('collections', []):
                            # Already stored and filed: nothing needs writing or
                            # recognizing again. This also reuses a managed view
                            # whose private original matches this source digest.
                            row.update(status='complete', attachment=existing['data']['key'], parent=parent_key)
                            if number % 20 == 0:
                                self.save(plan)
                            continue
                    if not existing and candidate_references(row["info"], catalog):
                        raise PilotError("A matching citation was added after scanning; check its existing attachment.")
                    info = inspect_document(path, evidence=True)
                    row["status"] = "applying"
                    self.save(plan)
                    result = client.review_action("bulk_import", {"source": str(path), "root": plan["root"],
                        "digest": row["digest"], "md5": digest_file(path, "md5"), "collection": plan["collection"],
                        "existing": existing["data"]["key"] if existing else "",
                        "existing_md5": digest_file(existing["path"], "md5") if existing else "",
                        "lookup": plan["lookup"], "dois": info.get("dois", []), "evidence": info.get("evidence", ""),
                        "title": info["title"] or path.stem})
                    deadline = time.monotonic() + 120
                    while result.get("pending"):
                        if worker.stop.wait(.2):
                            raise PilotError("Stopped. Zotero may finish the current file; rescan to resume without duplicates.")
                        if time.monotonic() > deadline:
                            raise TransportInterrupted("Zotero is still processing this file. The batch is saved; retry to resume without duplicates.")
                        result = client.review_action("bulk_import_status", {"digest": row["digest"], "collection": plan['collection']})
                    if result.get("error"):
                        raise PilotError(result["error"])
                    if result.get("issues"):
                        row["issues"].extend(result["issues"])
                    row.update({"status": "complete", "attachment": result["attachment"], "parent": result["parent"]})
                    result['reference'] = worker.apply_document_keywords(client, result['parent'], Path(result['path']), digest=row['digest'])
                    value = {"data": result["data"], "path": result["path"], "digest": row["digest"]}
                    indexed[row["digest"]] = [value]
                    catalog["attachments"].append(value)
                    catalog["parents"][result["parent"]] = result["reference"]
                except TransportInterrupted as error:
                    self.save(plan)
                    worker.last = {'state': 'waiting', 'message': str(error)}
                    return worker.status()
                except Exception as error:
                    # The native import may have completed before a transport
                    # interruption. A rescan detects its actual stored bytes.
                    row["status"] = "pending"
                    row["issues"].append(str(error))
                self.save(plan)
            self.save(plan)
            if any(row['kind'] == 'cloud' for row in worker.review.rows()):
                # Import changes which tablet documents already have a Zotero
                # counterpart; do not leave the visible review snapshot stale.
                worker.refresh_review_policy(client, catalog)
            worker.last = {"state": "ready", "message": "Bulk import saved. Original Windows files remain in place."}
            return worker.status()
        finally:
            client.close()


def review_policy(rows, catalog, documents, mappings, *, cancelled=lambda: False, cache=None):
    """Only material identity/file problems hold up a routine batch.

    No missing author, year, DOI, journal, or low OCR confidence rule appears
    here. Citation quality remains visible in Zotero and is not a reading gate.
    """
    indexed, by_key = library_index(catalog, documents, cancelled=cancelled, cache=cache)
    outcomes = {}
    for row in rows:
        payload, issues = row["payload"], []
        if payload.get('repair_required'):
            issues.append(payload['repair_required'])
        if row["kind"] not in {"zotero", "inbox", "cloud"}:
            outcomes[row["id"]] = ["A linked document or folder has conflicting changes."]
            continue
        path = Path(payload["path"])
        if not path.is_file():
            issues.append("The local file is unavailable.")
        # A failed extraction is different from a readable image-only PDF.
        for warning in payload.get("details", {}).get("review_reasons", []):
            if any(term in warning.casefold() for term in ("could not read", "could not extract metadata", "encrypted", "password")):
                issues.append("The file needs a readability check.")
        matches = payload.get("matches", [])
        if not matches and payload.get("possible_tablet_matches"):
            issues.append("A tablet PDF has the same name but different content; check the editions before uploading another copy.")
        if len(matches) > 1:
            issues.append("More than one identical counterpart exists; choose the intended copy.")
        if len(indexed.get(row["digest"], [])) > 1:
            issues.append("Identical content belongs to several Zotero attachments.")
        parent = payload.get("parent", "")
        details = payload.get("details", {})
        if details.get('filename_needs_review'):
            issues.append('Choose a readable name for this PDF before filing it.')
        if details.get("is_supplementary_material") or re.search(r"(?:^|[_ -])si$", path.stem, re.I):
            issues.append("Confirm the supporting information's main reference before sending it.")
        if parent:
            record = catalog["parents"].get(parent, {})
            duplicate_parents = [p for p in candidate_references({"title": record.get("title", ""), "dois": [record.get("DOI", "")]}, catalog) if p["key"] != parent]
            if duplicate_parents:
                issues.append("Another Zotero reference may describe the same work; check the references or versions.")
            homes = set(record.get("collections", [])) & set(mappings)
            if len(homes) > 1:
                issues.append("This reference has several tablet destinations; choose one home.")
            key = payload.get("attachment")
            siblings = [r for r in catalog["attachments"] if r["data"].get("parentItem") == parent
                        and r["data"]["key"] != key and Path(r["path"]).suffix.lower() == ".pdf"]
            if siblings and path.suffix.lower() == ".pdf":
                issues.append("This reference has multiple PDFs; choose its original or supporting file before linking.")
        if row["kind"] == "zotero" and row["identity"] in by_key and by_key[row["identity"]]["data"].get("linkMode") == "linked_file":
            issues.append("This PDF is linked to an external Windows file; store a Zotero copy before tablet updates.")
        outcomes[row["id"]] = list(dict.fromkeys(issues))
    return outcomes
