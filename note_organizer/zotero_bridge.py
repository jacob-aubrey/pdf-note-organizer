"""A scoped, additive Zotero/reMarkable bridge built on existing adapters.

Collection/PDF additions travel both ways. Only tablet revisions update managed
annotated PDFs. Moves, deletions, and changed desktop originals require review.
The bridge never guesses paper identity from titles, authors or DOI.
"""
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from types import SimpleNamespace
import uuid
from zipfile import BadZipFile

import pymupdf

from .remarkable_cloud import CloudItem, CloudError, atomic_write
from .remarkable_pdf import annotated_pdf, RENDER_REVISION, UnsupportedAnnotations
from .remarkable_sources import save_source_bundle, source_bundle
from .zotero_pilot import (AuthorizationRequired, Ledger, Paper, PilotError,
                           TransportInterrupted, publish, stable_key, marker)


class BridgeState(Ledger):
    def __init__(self, directory):
        super().__init__(directory)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS bridge_values (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def read(self, key, default=None):
        with self.connect() as db:
            row = db.execute("SELECT value FROM bridge_values WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def write(self, key, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO bridge_values VALUES(?,?)", (key, json.dumps(value)))


def descendants(records, root, key, parent):
    """Validate ancestry before any write; no recursive loops or truncated trees."""
    by_id = {key(row): row for row in records}
    if len(by_id) != len(records) or root not in by_id:
        raise PilotError("The selected sync root is missing or its catalog is ambiguous.")
    result = {}
    for identity, row in by_id.items():
        seen, cursor, depth = set(), identity, 0
        while cursor:
            if cursor in seen:
                raise PilotError("A folder catalog contains a cycle. No synchronization was attempted.")
            seen.add(cursor)
            if cursor == root:
                result[identity] = (row, depth)
                break
            ancestor = by_id.get(cursor)
            if ancestor is None:
                raise PilotError("A folder catalog is incomplete. Retry after synchronization finishes.")
            cursor, depth = parent(ancestor) or "", depth + 1
            if cursor == "trash":
                break  # Tablet trash is a virtual container outside every root.
    return result


def _sha(data):
    return hashlib.sha256(data).hexdigest()


class Bridge:
    def __init__(self, zotero, cloud, state, zotero_root, cloud_root, *, saved_annotations=None, review_policy=None, follow_changes=False, progress=None, exclusions=None):
        self.zot, self.cloud, self.state = zotero, cloud, state
        self.zroot, self.croot = zotero_root, str(uuid.UUID(cloud_root))
        # An optional selected-paper transcript provider can reuse saved Notable
        # text. It must resolve by tablet UUID, never title or similar keywords.
        self.saved_annotations = saved_annotations or (lambda item_id: ())
        self.review_policy = review_policy
        self.follow_changes = follow_changes
        self.progress = progress or (lambda message: None)
        self.exclusions = exclusions or {'zotero': set(), 'tablet': set(), 'documents': set(), 'sources': set()}
        self.namespace = "notable-bridge-" + _sha(json.dumps([zotero.server_id, zotero_root, self.croot]).encode())[:24]
        self.publisher = Ledger(state.directory / "publisher")
        self.sources = SimpleNamespace(path=state.directory / "sources" / "library.sqlite3")

    def run(self, *, apply=False):
        with self.state.lock():
            self.state.bind(self.zot.server_id, self.namespace)
            return self._run(apply)

    @contextmanager
    def _document_errors(self, reviews, *, cloud=None, attachment=None, suspended=None):
        """Keep a damaged or unavailable paper from blocking unrelated work."""
        try:
            yield
        except (InterruptedError, AuthorizationRequired, TransportInterrupted):
            # Cancellation and lost permission belong to the whole operation.
            raise
        except (PilotError, CloudError, OSError, ValueError, KeyError, BadZipFile,
                pymupdf.FileDataError, pymupdf.EmptyFileError) as error:
            if isinstance(error, CloudError) and "authorization expired" in str(error).lower():
                raise
            identity = {"cloud": cloud} if cloud else {"attachment": attachment}
            reviews.append({**identity, "reason": str(error) or "This paper could not be processed. Its source was retained."})
            if cloud and suspended is not None:
                suspended.add(cloud)

    def _run(self, apply):
        collections = [r for r in self.zot.collections() if not r.get("deleted")]
        catalog = self.cloud.library()
        zscope = descendants(collections, self.zroot, lambda r: r["key"], lambda r: r.get("parentCollection"))
        cfolders = [r for r in catalog if not r.deleted and r.kind == "CollectionType"]
        cscope = descendants(cfolders, self.croot, lambda r: r.id, lambda r: r.parent)
        from .zotero_connections import filtered_scope
        zscope = filtered_scope(zscope, self.exclusions['zotero'], lambda r: r['key'], lambda r: r.get('parentCollection'), self.zroot)
        cscope = filtered_scope(cscope, self.exclusions['tablet'], lambda r: r.id, lambda r: r.parent, self.croot)
        zby = {key: row for key, (row, _) in zscope.items()}
        cby = {key: row for key, (row, _) in cscope.items()}
        maps = self.state.read("folders", {self.zroot: {"cloud": self.croot, "root": True}})
        documents = self.state.read("documents", {})
        reports, reviews = [], []

        def save():
            if apply:
                self.state.write("folders", maps)
                self.state.write("documents", documents)

        def zwrite():
            if apply:
                self.zot.authorize()

        save()  # Persist the root-only mapping even when both subtrees are empty.

        # Recover uncertain folder creation using the identities committed before
        # the request. A confirmed deletion is never treated as an incomplete job.
        for zk, link in list(maps.items()):
            ck = link["cloud"]
            if link.get("pending") == "cloud" and ck not in cby:
                if zk not in zby:
                    raise PilotError("A pending collection left the selected Zotero subtree.")
                if apply:
                    row = self.cloud.create_folder(link["name"], link["cparent"], ck, self.croot)
                    cby[ck] = row
                    link.pop("pending")
                    save()
            elif link.get("pending") == "zotero" and zk not in zby:
                if ck not in cby:
                    raise PilotError("A pending tablet folder left the selected subtree.")
                if apply:
                    zwrite()
                    zby[zk] = self.zot.create("collection", {"key": zk, "name": link["name"],
                                                          "parentCollection": link["zparent"]})
                    link.pop("pending")
                    save()
            elif zk not in zby or ck not in cby:
                raise PilotError("A linked collection/folder was deleted or moved outside the selected roots. Review it before retrying.")
            if zk in zby and ck in cby and link.get("pending"):
                link.pop("pending")
                save()
            if zk in zby and ck in cby and not link.get("root"):
                if not self.follow_changes and (zby[zk].get("parentCollection") != link["zparent"] or cby[ck].parent != link["cparent"]
                        or zby[zk]["name"] != link["name"] or cby[ck].name != link["name"]):
                    raise PilotError("A linked folder was renamed or moved. Existing files were retained; review its mapping.")

        # Discover parent before child in either direction. A unique sibling name
        # can link folders; paper identity always requires a recorded source ID.
        pending_z, pending_c = set(zby) - set(maps), set(cby) - {v["cloud"] for v in maps.values()}
        while pending_z or pending_c:
            progressed = False
            for zp, parent_link in list(maps.items()):
                cp = parent_link["cloud"]
                zs = [k for k in pending_z if zby[k].get("parentCollection") == zp]
                cs = [k for k in pending_c if cby[k].parent == cp]
                zcounts = Counter(zby[k]["name"] for k in zs)
                ccounts = Counter(cby[k].name for k in cs)
                if any(n > 1 for n in zcounts.values()) or any(n > 1 for n in ccounts.values()):
                    raise PilotError("Duplicate sibling folder names need an explicit mapping before sync.")
                for zk in zs:
                    name = zby[zk]["name"]
                    match = next((k for k in cs if cby[k].name == name), None)
                    ck = match or str(uuid.uuid5(uuid.NAMESPACE_URL, self.namespace + "/collection/" + zk))
                    maps[zk] = {"cloud": ck, "name": name, "zparent": zp, "cparent": cp,
                                **({} if match else {"pending": "cloud"})}
                    save()
                    reports.append({"action": "link_folders" if match else "folder_to_tablet", "zotero": zk, "cloud": ck})
                    if match:
                        pending_c.remove(match)
                    elif apply:
                        cby[ck] = self.cloud.create_folder(name, cp, ck, self.croot)
                        maps[zk].pop("pending")
                        save()
                    else:
                        cby[ck] = CloudItem(ck, "", name, cp, "CollectionType", False, [])
                    pending_z.remove(zk)
                    progressed = True
                for ck in cs:
                    if ck not in pending_c:
                        continue
                    zk = stable_key(self.namespace, "collection", ck)
                    if zk in zby:
                        raise PilotError("A generated collection ID is already in use. No existing collection was adopted.")
                    name = cby[ck].name
                    maps[zk] = {"cloud": ck, "name": name, "zparent": zp, "cparent": cp, "pending": "zotero"}
                    save()
                    reports.append({"action": "folder_to_zotero", "zotero": zk, "cloud": ck})
                    if apply:
                        zwrite()
                        zby[zk] = self.zot.create("collection", {"key": zk, "name": name, "parentCollection": zp})
                        maps[zk].pop("pending")
                        save()
                    else:
                        zby[zk] = {"key": zk, "name": name, "parentCollection": zp}
                    pending_c.remove(ck)
                    progressed = True
            if not progressed:
                raise PilotError("Some folders cannot be mapped inside the selected roots.")

        reverse = {v["cloud"]: k for k, v in maps.items()}
        if len(reverse) != len(maps):
            raise PilotError("More than one collection maps to the same tablet folder.")
        for zk, link in maps.items():
            if link.get("root"):
                continue
            if self.follow_changes:
                tablet = cby[link["cloud"]]
                before = [link["name"], link["zparent"]]
                desktop = [zby[zk]["name"], zby[zk].get("parentCollection")]
                remote = [tablet.name, reverse.get(tablet.parent)]
                if not remote[1] or desktop[1] not in maps:
                    raise PilotError("A mapped folder moved outside the selected tree. Review its scope before syncing.")
                if desktop != before and remote != before and desktop != remote:
                    conflict = {"type": "folder", "zotero": zk, "cloud": tablet.id, "desktop": desktop, "tablet": remote,
                                "cloud_hash": tablet.hash, "version": zby[zk].get("version", 0)}
                    if self.review_policy:
                        from .zotero_review import fingerprint
                        self.review_policy.offer("conflict", zk, fingerprint(conflict), conflict)
                    reviews.append({"collection": zk, "reason": "This folder changed on both devices. Choose a version in Notable review."})
                    return {"mode": "apply" if apply else "plan", "actions": reports, "review": reviews, "folders": len(maps), "documents": len(documents)}
                chosen = desktop if desktop != before else remote
                if apply and desktop != remote:
                    if desktop != before:
                        cby[tablet.id] = self.cloud.update_item(tablet.id, expected_hash=tablet.hash, name=chosen[0], parent=maps[chosen[1]]["cloud"], scope_id=self.croot)
                    else:
                        zwrite()
                        zby[zk]["name"], zby[zk]["parentCollection"] = chosen
                        self.zot.update_collection(zby[zk])
                if apply:
                    link.update(name=chosen[0], zparent=chosen[1], cparent=maps[chosen[1]]["cloud"])
                    save()
                continue
            if (zby[zk].get("parentCollection") != link["zparent"] or cby[link["cloud"]].parent != link["cparent"]
                    or zby[zk]["name"] != link["name"] or cby[link["cloud"]].name != link["name"]):
                raise PilotError("A linked folder was renamed or moved. Existing files were retained; review its mapping.")

        # Each Zotero child PDF is a distinct document (including SI), with its
        # own immutable original. Returned marked attachments never re-enter this
        # upload path. Multiple collections need an explicit primary location.
        references = {}
        suspended = (self.review_policy.suspended_documents() if self.review_policy else set()) | self.exclusions['documents']
        if self.follow_changes:
            from pathlib import Path
            from .zotero_review import fingerprint
            by_id = {item.id: item for item in catalog}
            for identity, row in documents.items():
                if identity in suspended or not row.get("parent"):
                    continue
                with self._document_errors(reviews, cloud=identity, suspended=suspended):
                    item = by_id.get(identity)
                    parent = self.zot.get("item", row["parent"])
                    if not item or item.deleted or item.parent not in reverse or not parent or parent.get("deleted"):
                        continue
                    homes = [k for k in parent.get("collections", []) if k in maps]
                    home = row["collection"] if row["collection"] in homes else homes[0] if len(homes) == 1 else None
                    if not home:
                        reviews.append({"cloud": identity, "reason": "Choose one tablet home; removing a collection membership does not delete the paper."})
                        continue
                    key = row.get("view_key") or row.get("source_key")
                    if not key:
                        continue
                    path = self.zot.file_path(key)
                    # Preserve any independent names established during adoption.
                    row.setdefault("desktop_name", path.stem)
                    desktop = [path.stem, home]
                    remote = [item.name, reverse[item.parent]]
                    old_desktop = [row["desktop_name"], row["collection"]]
                    old_remote = [row["name"], row["collection"]]
                    zdiff, cdiff = desktop != old_desktop, remote != old_remote
                    if zdiff and cdiff and desktop != remote:
                        conflict = {"type": "paper", "cloud": identity, "zotero": parent["key"], "desktop": desktop, "tablet": remote,
                                    "cloud_hash": item.hash, "version": parent.get("version", 0), "file_md5": hashlib.md5(path.read_bytes()).hexdigest()}
                        self.review_policy.offer("conflict", identity, fingerprint(conflict), conflict)
                        suspended.add(identity)
                        reviews.append({"cloud": identity, "reason": "This paper was renamed or moved on both devices. Choose a version in review."})
                        continue
                    if (zdiff or cdiff) and apply:
                        chosen = desktop if zdiff else remote
                        if zdiff and desktop != remote:
                            changed = self.cloud.update_item(identity, expected_hash=item.hash, name=chosen[0], parent=maps[chosen[1]]["cloud"], scope_id=self.croot)
                            catalog[catalog.index(item)] = changed
                        elif cdiff and desktop != remote:
                            self.set_desktop_document(row, chosen[0], chosen[1], maps)
                        row.update(name=chosen[0], desktop_name=chosen[0], collection=chosen[1], tablet_parent=maps[chosen[1]]["cloud"])
                        reports.append({"action": "paper_location_updated", "cloud": identity})
                    save()
        for zk in zby:
            if not apply and zk not in zscope:
                continue
            for row in self.zot.collection_items(zk):
                if row.get("itemType") not in {"attachment", "note", "annotation"} and not row.get("deleted"):
                    references[row["key"]] = row
        for parent in references.values():
            homes = [k for k in parent.get("collections", []) if k in maps]
            for attachment in self.zot.children(parent["key"]):
                if (attachment.get("itemType") != "attachment" or attachment.get("deleted")
                        or attachment.get("contentType") != "application/pdf"
                        or "Notable pilot:" in attachment.get("note", "")):
                    continue
                source_key = attachment["key"]
                if source_key in self.exclusions['sources']:
                    continue
                with self._document_errors(reviews, attachment=source_key):
                    existing = next(((ck, d) for ck, d in documents.items() if d.get("source_key") == source_key), None)
                    data = self.zot.file_path(source_key).read_bytes()
                    baseline = _sha(data)
                    approval = self.review_policy.approval("zotero", source_key, baseline) if self.review_policy else {}
                    # A reference can have several PDFs, each with its own tablet
                    # home. Research memberships do not override that choice.
                    chosen = existing[1]["collection"] if existing else (approval or {}).get("collection")
                    zk = chosen if chosen in homes else homes[0] if len(homes) == 1 else None
                    if not zk:
                        reviews.append({"attachment": source_key, "reason": "Choose one tablet destination for this PDF inside the sync subtree."})
                        continue
                    if existing:
                        ck, old = existing
                        if ck in suspended:
                            continue
                        if old["baseline"] != baseline or old["collection"] != zk or old["parent"] != parent["key"]:
                            reviews.append({"attachment": source_key, "reason": "The desktop original or its collection changed; it was not sent back to the tablet."})
                        continue
                    if approval is None:
                        reviews.append({"attachment": source_key, "reason": "Review the filename and tablet destination before sending this new document."})
                        continue
                    ck = str(uuid.uuid5(uuid.NAMESPACE_URL, self.namespace + "/pdf/" + source_key))
                    documents[ck] = {"origin": "zotero", "source_key": source_key, "parent": parent["key"],
                                     "collection": zk, "baseline": baseline, "uploaded": False,
                                     "role": "si" if approval.get("document_type") == "supporting_information" else "main",
                                     "tablet_parent": maps[zk]["cloud"],
                                     "name": (parent.get("title") or attachment.get("title") or source_key)[:180]}
                    # Include a child label when a reference has several PDF files.
                    label = attachment.get("title", "")
                    if label and label != parent.get("title"):
                        documents[ck]["name"] += " - " + label[:60]
                    if approval.get("filename"):
                        from pathlib import Path
                        documents[ck]["name"] = Path(approval["filename"]).stem
                    original = self.state.directory / "originals" / (baseline + ".pdf")
                    if apply:
                        if not original.exists():
                            atomic_write(original, data, require_absent=True)
                        elif _sha(original.read_bytes()) != baseline:
                            raise PilotError("A retained desktop original changed. It was not uploaded.")
                    save()
                    reports.append({"action": "pdf_to_tablet", "attachment": source_key, "cloud": ck})

        cloud_pdfs = {r.id: r for r in catalog if not r.deleted and r.is_pdf and r.parent in reverse}
        for identity in suspended:
            cloud_pdfs.pop(identity, None)
        for ck, row in list(documents.items()):
            if ck in suspended:
                continue
            if row["origin"] != "zotero":
                continue
            with self._document_errors(reviews, cloud=ck, suspended=suspended):
                parent, source = self.zot.get("item", row["parent"]), self.zot.get("item", row["source_key"])
                if (not parent or not source or parent.get("deleted") or source.get("deleted")
                        or source.get("parentItem") != row["parent"]
                        or row["collection"] not in parent.get("collections", [])):
                    reviews.append({"cloud": ck, "reason": "The linked Zotero source was deleted or moved. No PDF was recreated."})
                    # Do not publish or upload this stale mapping later in the run.
                    cloud_pdfs.pop(ck, None)
                    continue
                if ck not in cloud_pdfs and row["uploaded"]:
                    reviews.append({"cloud": ck, "reason": "Linked tablet PDF is missing or moved; it was not recreated."})
                    continue
                if ck not in cloud_pdfs and apply:
                    original = self.state.directory / "originals" / (row["baseline"] + ".pdf")
                    data = original.read_bytes()
                    if _sha(data) != row["baseline"]:
                        raise PilotError("A staged original changed. Upload stopped.")
                    item = self.cloud.upload_pdf(data, row["name"], maps[row["collection"]]["cloud"], ck, self.croot)
                    cloud_pdfs[ck] = item
                    # A lost response leaves uploaded=False and the persisted ID;
                    # next run validates its baseline instead of creating a new PDF.
                if ck in cloud_pdfs:
                    row["uploaded"] = True
                    save()

        for number, (ck, item) in enumerate(cloud_pdfs.items(), 1):
            if ck in suspended:
                continue
            with self._document_errors(reviews, cloud=ck):
                row = documents.get(ck)
                self.progress(f'{"Syncing linked" if row else "Checking new tablet"} paper {number} of {len(cloud_pdfs)}…')
                zk = reverse[item.parent]
                if row and row["collection"] != zk:
                    reviews.append({"cloud": ck, "reason": "Linked tablet PDF moved; review the primary collection."})
                    continue
                bundle = self.cloud.pdf_bundle(item)
                baseline = _sha(bundle[ck + ".pdf"])
                if row and row["baseline"] != baseline:
                    reviews.append({"cloud": ck, "reason": "The tablet PDF baseline changed; annotations were not applied to a different edition."})
                    continue
                if not row:
                    approval = self.review_policy.approval("cloud", ck, baseline) if self.review_policy else {}
                    if approval is None:
                        reviews.append({"cloud": ck, "reason": "Review this new tablet document before importing it."})
                        continue
                    row = {"origin": "cloud", "parent": "", "collection": zk, "baseline": baseline,
                           "role": "si" if approval.get("document_type") == "supporting_information" else "main",
                           "uploaded": True, "name": item.name, "tablet_parent": item.parent}
                    if approval.get("parent"):
                        row["parent"] = approval["parent"]
                    documents[ck] = row
                    save()
                if self.review_policy and row["origin"] == "cloud" and not row.get("parent"):
                    raise PilotError("The approved Zotero reference is unavailable. Review this paper before importing it; no replacement reference was created.")
                if self.review_policy and "role" not in row:
                    approval = self.review_policy.approval("cloud", ck, baseline)
                    if approval is None and row.get("source_key"):
                        approval = self.review_policy.approval("zotero", row["source_key"], baseline)
                    row["role"] = "si" if (approval or {}).get("document_type") == "supporting_information" else "main"
                if not apply:
                    reports.append({"action": "tablet_to_zotero", "cloud": ck, "collection": zk})
                    continue
                save_source_bundle(self.sources, item, bundle)
                # Rendering only retained, integrity-checked source bytes also makes
                # later retries independent of mutable in-memory download objects.
                retained_bundle = source_bundle(self.sources, ck, revision=item.hash)
                from .zotero_tags import render_fingerprint
                render_id = [render_fingerprint(ck, retained_bundle), RENDER_REVISION]
                cached = row.get("rendered", {})
                output = self.state.directory / "rendered" / (cached.get("sha256", "missing") + ".pdf")
                if cached.get("input") == render_id and output.exists():
                    digest = cached["sha256"]
                    if _sha(output.read_bytes()) != digest:
                        raise PilotError("A retained annotated PDF changed. It was preserved for review.")
                else:
                    try:
                        rendered = annotated_pdf(item, retained_bundle)
                    except UnsupportedAnnotations as error:
                        reviews.append({"cloud": ck, "reason": str(error)})
                        continue
                    digest = _sha(rendered)
                    output = self.state.directory / "rendered" / (digest + ".pdf")
                    if not output.exists():
                        atomic_write(output, rendered, require_absent=True)
                    row["rendered"] = {"input": render_id, "sha256": digest}
                    save()
                annotations = tuple(self.saved_annotations(ck))
                if self.review_policy and row.get("source_key") and not row.get("view_key"):
                    source = row["source_key"]
                    if self.publisher.get(ck)["published"]:
                        row["view_key"] = stable_key(self.namespace, "attachment", ck)
                    else:
                        original = self.state.directory / "originals" / (baseline + ".pdf")
                        original_md5 = hashlib.md5(original.read_bytes()).hexdigest()
                        adopted = self.zot.review_action("adopt", {"key": source, "parent": row["parent"], "md5": original_md5,
                                                                 "marker": marker(self.namespace, ck)})
                        row["view_key"] = source if adopted["adopted"] else stable_key(self.namespace, "attachment", ck)
                        row["desktop_annotations_preserved"] = adopted["native"]
                        if adopted["adopted"]:
                            self.publisher.save(ck, md5=original_md5)
                    save()
                paper = Paper(ck, output, digest, {"title": row["name"]}, role=row.get("role", "main"), annotations=annotations,
                              source_attachment_key=row.get("source_key", "") if row.get("source_key") != row.get("view_key") else "",
                              filename=row["name"] + ".pdf" if self.review_policy else "")
                parents = {ck: row["parent"]} if row.get("parent") else None
                result = publish(self.zot, self.publisher, self.namespace, [paper], apply=True,
                                 collection_key=zk, reference_keys=parents,
                                 attachment_keys={ck: row["view_key"]} if row.get("view_key") else None)["papers"][0]
                if row["origin"] == "cloud":
                    row["parent"] = result["reference_key"]
                row["revision"] = item.hash
                row["view_key"] = result["attachment_key"]
                if self.follow_changes and "desktop_name" not in row:
                    row["desktop_name"] = self.zot.file_path(row["view_key"]).stem
                save()
                reports.append({**result, "action": "tablet_to_zotero", "publication_action": result["action"], "cloud": ck})
                from .remarkable_pdf import page_map
                with pymupdf.open(stream=bundle[ck + '.pdf'], filetype='pdf') as original_pdf:
                    row['page_map'] = [pid for pid, _ in page_map(json.loads(bundle[ck + '.content']), len(original_pdf))]
                row['page_map_digest'] = digest
                save()
                self._tags(row['parent'], bundle, ck, row, save)
                self.progress(f'Received tablet PDF {number} of {len(cloud_pdfs)}…')
        return {"mode": "apply" if apply else "plan", "actions": reports, "review": reviews,
                "folders": len(maps), "documents": len(documents)}

    def set_desktop_document(self, row, name, home, maps):
        """Move only the tablet-home membership; keep all research categories."""
        from .sorting.core_logic import validate_document_filename
        parent = self.zot.get("item", row["parent"])
        if not parent or parent.get("deleted"):
            raise PilotError("The Zotero reference was trashed. Its tablet copy was retained.")
        parent["collections"] = sorted((set(parent.get("collections", [])) - {row["collection"]}) | {home})
        self.zot.authorize()
        self.zot.update(parent)
        for key in {row.get("source_key"), row.get("view_key")} - {None, ""}:
            path = self.zot.file_path(key)
            filename = validate_document_filename(name + path.suffix, path.suffix)
            self.zot.review_action("rename", {"key": key, "filename": filename, "md5": hashlib.md5(path.read_bytes()).hexdigest()})

    def _tags(self, parent_key, bundle, cloud_id, row, save):
        from .zotero_tags import reconcile
        # The bundle revision is the only revision whose tags were observed.
        from .remarkable_cloud import CloudItem
        item = CloudItem(cloud_id, row['revision'], row['name'], row.get('tablet_parent', ''), 'DocumentType', False, [])
        reconcile(self, parent_key, item, bundle, row, save)
