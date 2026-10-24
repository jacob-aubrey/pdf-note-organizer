"""Private JSON transport for the Zotero plugin's managed background process.

The plugin owns setup and review. No terminal or Python installation is part of
the user workflow. New inputs remain gated by durable, content-bound approvals.
"""
from contextlib import contextmanager, redirect_stdout
import hashlib
import json
import logging
import mimetypes
from pathlib import Path
import queue
import re
import sys
import threading
import time

from .remarkable_cloud import CloudClient, CloudError, TokenVault, atomic_write
from .zotero_bridge import Bridge, BridgeState, descendants
from .zotero_pilot import AuthorizationRequired, LocalZotero, PilotError, TransportInterrupted, stable_key
from .zotero_review import ReviewStore, fingerprint
from . import zotero_connections as connections


TYPE_MAP = {"journal_article": "journalArticle", "preprint": "preprint", "conference_paper": "conferencePaper",
            "book_chapter": "bookSection", "book": "book", "thesis_dissertation": "thesis",
            "technical_report": "report", "white_paper": "report", "guideline_standard": "standard",
            "presentation_poster": "presentation", "letter_note": "letter", "patent": "patent",
            "patent_application": "patent", "web_or_other": "document", "unknown": "document"}


def file_sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def citation_signature(record):
    return fingerprint({key: (record or {}).get(key, "") for key in (
        "title", "itemType", "creators", "date", "DOI", "publicationTitle", "publisher", "university", "extra")})


def write_packet(transport, packet):
    # JSON escapes preserve every character without depending on the Windows
    # pipe's locale encoding (often cp1252, even in a frozen executable).
    transport.write(json.dumps(packet, ensure_ascii=True) + '\n')
    transport.flush()


def progress_links(worker):
    """Small live connection updates without polling the serialized API."""
    state = getattr(worker, 'state', None)
    if state is None:
        return None
    fields = ('name', 'parent', 'collection', 'revision', 'view_key', 'desktop_annotations_preserved')
    return [{'cloud': key, **{field: row[field] for field in fields if field in row}}
            for key, row in state.read('documents', {}).items()]


class Worker:
    def __init__(self, directory, port=23119, *, resources=None, zotero_factory=None, cloud_factory=None):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.resources = Path(resources or Path(__file__).resolve().parents[1])
        self.port, self.stop = int(port), threading.Event()
        self.pause_pending = threading.Event()
        path = self.directory / "config.json"
        self.config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        pause_marker = self.directory / 'pause-requested.json'
        if pause_marker.exists():
            self.config['sync_paused'] = True
            self.save()
            pause_marker.unlink()
        self._open_connection()
        self.zotero_factory, self.cloud_factory = zotero_factory, cloud_factory
        self.last = {'state': 'setup_required' if not self.config.get('tablet_root') else 'paused' if self.config.get('sync_paused') else 'ready',
                     'message': 'Sync paused. Click Sync now when ready.' if self.config.get('sync_paused') else ''}
        self.collections = []
        self.progress = lambda message: None
        self.file_digests = {}
        from .zotero_bulk import BulkLibrary
        self.bulk = BulkLibrary(self)

    def _open_connection(self):
        self.connection_dir = connections.state_directory(self.directory, self.config)
        self.review = ReviewStore(self.connection_dir / 'review')
        self.state = BridgeState(self.connection_dir / 'bridge')

    def _connection_snapshot(self):
        return fingerprint({'config': self.config, 'values': connections.values(self.directory, self.config),
                            'review': file_sha(self.review.path)})

    def _begin_operation(self):
        if self.pause_pending.is_set():
            raise InterruptedError('Sync paused')
        self.stop.clear()
        if self.pause_pending.is_set():
            self.stop.set()
            raise InterruptedError('Sync paused')

    def pause_sync(self):
        self.stop.set()
        proposed = {**self.config, 'sync_paused': True}
        atomic_write(self.directory / 'config.json', json.dumps(proposed, ensure_ascii=False).encode())
        self.config = proposed
        (self.directory / 'pause-requested.json').unlink(missing_ok=True)
        self.pause_pending.clear()
        self.last = {'state': 'paused', 'message': 'Sync paused. Your papers and notes stay in place.'}
        return self.status()

    def save(self):
        atomic_write(self.directory / "config.json", json.dumps(self.config, ensure_ascii=False).encode())

    def zotero(self, *, interactive=False, ocr=False):
        if self.zotero_factory:
            return self.zotero_factory()
        printed, handwriting = None, None
        if ocr and self.config.get("ocr", True):
            from .printed_ocr import PrintedOCR
            from .handwriting_ocr import HandwritingOCR
            printed = PrintedOCR(self.resources / "models/printed", self.directory / "printed-cache", cancelled=self.stop.is_set)
            handwriting = HandwritingOCR(self.resources / "models/handwriting", self.directory / "handwriting-cache", cancelled=self.stop.is_set)
        client = LocalZotero(self.port, printed_ocr=printed, handwriting_ocr=handwriting,
                             grant_store=TokenVault(self.directory / "zotero-grant.dpapi"), interactive=interactive)
        if self.config.get("server_id") and client.server_id != self.config["server_id"]:
            client.close()
            raise PilotError("A different Zotero library is open. Reconnect in Setup before using saved mappings.")
        return client

    def cloud(self):
        if self.cloud_factory:
            return self.cloud_factory()
        token = TokenVault(self.directory / "tablet-token.dpapi").load()
        if not token:
            raise PilotError("Pair reMarkable from Setup first.")
        return CloudClient(token, cache_dir=self.directory / "blobs", stop=self.stop)

    def status(self):
        from .sorting.core_logic import DOCUMENT_TYPE_LABELS
        config = {k: v for k, v in self.config.items() if k != "server_id"}
        documents = self.state.read('documents', {})
        linked_sources = {row.get('source_key') for row in documents.values()}
        waiting = {row['approval'].get('source') or row['kind'] + ':' + row['identity']
                   for row in self.review.rows(pending_only=False)
                   if row['status'] == 'approved' and row['kind'] in {'cloud', 'zotero', 'inbox'}
                   and row['identity'] not in documents and row['approval'].get('source') not in linked_sources}
        return {"config": config, "status": self.last, "reviews": self.review.rows(),
                "deletions": self.review.deletions(), "local_deletions": self.review.local_deletions(), "types": DOCUMENT_TYPE_LABELS,
                "collections": self.collections, "mappings": self.state.read("folders", {}),
                "cleanup_pending": len(self.review.cleanups()), "bulk": self.bulk.read(),
                'filing_summary': {'approved_waiting_sync': len(waiting), 'linked': len(documents),
                                   'pdfs_received': sum(bool(row.get('revision')) for row in documents.values())},
                "links": [{"cloud": key, **row, **self.review.link_control(key)} for key, row in self.state.read("documents", {}).items()],
                'connection': {'linked_papers': len(self.state.read('documents', {})),
                  'previous': [{**{key: row.get(key, '') for key in ('zotero_root', 'tablet_root', 'zotero_path', 'tablet_path')},
                                'linked_papers': len(connections.values(self.directory, row)['documents'])}
                               for row in self.config.get('connection_history', [])]}}

    def connect(self):
        client = self.zotero(interactive=True)
        try:
            client.authorize()
            self.config["server_id"] = client.server_id
            self.collections = client.collections()
            self.save()
            return {"connected": True, "collections": self.collections}
        finally:
            client.close()

    def _tag_plans(self):
        path = self.directory / 'paper-tag-proposals.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

    def _save_tag_plans(self, plans):
        atomic_write(self.directory / 'paper-tag-proposals.json', json.dumps(plans, ensure_ascii=False).encode('utf-8'))

    def _paper_target(self, client, identity='', key=''):
        if bool(identity) == bool(key):
            raise PilotError('Choose one paper for tag suggestions.')
        if identity:
            row = self.review.row(identity)
            if not row or row['kind'] not in {'cloud', 'zotero', 'inbox'}:
                raise PilotError('Choose a current paper review.')
            path = client.file_path(row['identity']) if row['kind'] == 'zotero' else Path(row['payload']['path'])
            parent = row['payload'].get('parent', '')
            digest = file_sha(path)
            if digest != row['digest']:
                raise PilotError('The reviewed paper changed. Refresh it before checking tags.')
            target = 'review:' + identity
        else:
            item = client.get('item', key)
            if not item or item.get('deleted') or item.get('itemType') != 'attachment' or not item.get('parentItem'):
                raise PilotError('Choose a stored PDF with a parent reference.')
            path, parent = client.file_path(key), item['parentItem']
            digest, target = file_sha(path), 'item:' + key
        record = client.get('item', parent) if parent else None
        if parent and (not record or record.get('deleted')):
            raise PilotError('The paper reference is unavailable.')
        return {'target': target, 'identity': identity, 'key': key, 'path': str(path), 'digest': digest,
                'parent': parent, 'tags': (record or {}).get('tags', [])}

    def paper_tag_candidates(self, query=''):
        client = self.zotero()
        try:
            catalog = client.review_action('catalog')
            result = []
            for attachment in catalog['attachments']:
                parent = catalog['parents'].get(attachment['data'].get('parentItem'))
                if parent and Path(attachment['path']).suffix.lower() == '.pdf' and str(query).casefold() in parent.get('title', '').casefold():
                    result.append({'key': attachment['data']['key'], 'title': parent.get('title', ''), 'filename': Path(attachment['path']).name})
            return {'candidates': sorted(result, key=lambda row: row['title'].casefold())[:50], 'total': len(result)}
        finally:
            client.close()

    def suggest_paper_tags(self, identity='', key=''):
        from .zotero_tagging import analyse
        client = self.zotero()
        try:
            source = self._paper_target(client, identity, key)
            catalog = client.review_action('catalog')
            vocabulary = {tag['tag'] for parent in catalog['parents'].values() for tag in parent.get('tags', [])}
            self.progress('Reading stated keywords and preparing local tag suggestions…')
            proposal = {**source, **analyse(source['path'], vocabulary, [tag['tag'] for tag in source['tags']])}
            plans = self._tag_plans()
            previous = plans.get(source['target'], {})
            proposal['selected'] = previous.get('selected', []) if previous.get('digest') == source['digest'] else []
            proposal['token'] = fingerprint(proposal)
            plans[source['target']] = proposal
            self._save_tag_plans(plans)
            return {'proposal': proposal}
        finally:
            client.close()

    def save_paper_tags(self, target, token, selected):
        from .zotero_tags import names
        from .zotero_tagging import append_tags
        selected = names(selected)
        plans = self._tag_plans()
        proposal = plans.get(target)
        if not proposal or proposal['token'] != token or not set(selected) <= {row['tag'] for row in proposal['suggestions']}:
            raise PilotError('The tag suggestions changed. Check this paper again.')
        client = self.zotero()
        try:
            source = self._paper_target(client, proposal['identity'], proposal['key'])
            if any(source[field] != proposal[field] for field in ('path', 'digest', 'parent', 'tags')):
                raise PilotError('The paper or its tags changed. Check its suggestions again before saving.')
            if not proposal['identity']:
                record = client.get('item', source['parent'])
                updated = append_tags(record.get('tags', []), [row['tag'] for row in proposal['keywords']], selected)
                if updated != record.get('tags', []):
                    record['tags'] = updated
                    client.authorize(); client.update(record)
            proposal['selected'] = selected
            proposal['saved'] = True
            plans[target] = proposal
            self._save_tag_plans(plans)
            return {'saved': True, 'deferred_until_filing': bool(proposal['identity'])}
        finally:
            client.close()

    def apply_document_keywords(self, client, parent, path, identity='', digest=''):
        from .zotero_tagging import document_keywords, append_tags
        record = client.get('item', parent)
        if not record or record.get('deleted'):
            raise PilotError('The paper reference changed before its keyword tags could be saved.')
        existing = record.get('tags', [])
        keywords = document_keywords(path, [row['tag'] for row in existing])
        if digest and file_sha(path) != digest:
            raise PilotError('The paper changed while reading its keywords. Its existing tags were retained.')
        plan = self._tag_plans().get('review:' + identity, {}) if identity else {}
        accepted = plan.get('selected', []) if plan.get('saved') and plan.get('digest') == file_sha(path) else []
        updated = append_tags(existing, [row['tag'] for row in keywords], accepted)
        if updated != existing:
            record['tags'] = updated
            client.authorize(); client.update(record)
        return record

    def pair(self, code):
        self._begin_operation()
        client = CloudClient(stop=self.stop)
        token = client.pair(code)
        TokenVault(self.directory / "tablet-token.dpapi").save(token)
        return {"paired": True}

    def folders(self):
        self._begin_operation()
        client = self.zotero()
        try:
            self.collections = client.collections()
            return {"collections": self.collections, "folders": [
                {"id": item.id, "name": item.name, "parent": item.parent}
                for item in self.cloud().library() if not item.deleted and item.kind == "CollectionType"]}
        finally:
            client.close()

    def _setup_plan(self, values):
        self._begin_operation()
        from .sorting.core_logic import DOCUMENT_TYPES, validate_filename_template
        allowed = {"zotero_root", "tablet_root", "default_folder", "inbox", "templates", "automatic", "ocr"}
        if set(values) - allowed:
            raise PilotError("Unsupported setup field.")
        for kind, template in values.get("templates", {}).items():
            if kind not in DOCUMENT_TYPES:
                raise PilotError("Choose a supported document type.")
            if template:
                validate_filename_template(template)
        client = self.zotero()
        try:
            proposed = {**self.config, **values}
            collections = client.collections()
            zscope = descendants(collections, proposed["zotero_root"], lambda r: r["key"], lambda r: r.get("parentCollection"))
            folders = [r for r in self.cloud().library() if not r.deleted and r.kind == "CollectionType"]
            cscope = descendants(folders, proposed["tablet_root"], lambda r: r.id, lambda r: r.parent)
            if proposed.get("default_folder", proposed["tablet_root"]) not in cscope:
                raise PilotError("Choose a default tablet folder inside the selected scope.")
            inbox = str(proposed.get("inbox", "")).strip()
            if inbox:
                inbox_path = Path(inbox).resolve(strict=True)
                if not inbox_path.is_dir():
                    raise PilotError("Choose an existing ToSort folder.")
                catalog = client.review_action("catalog")
                # Do not scan Zotero's own storage as an intake folder.
                if any(Path(a["path"]).resolve().is_relative_to(inbox_path) for a in catalog["attachments"]):
                    raise PilotError("Choose a separate download folder, outside Zotero's managed storage.")
                proposed["inbox"] = str(inbox_path)
            def path(rows, identity, key, parent):
                by = {key(row): row for row in rows}
                names = []
                seen = set()
                while identity:
                    if identity in seen or identity not in by:
                        raise PilotError('The folder list changed. Refresh folders before saving.')
                    seen.add(identity)
                    row = by[identity]
                    names.insert(0, row['name'] if isinstance(row, dict) else row.name)
                    identity = parent(row)
                return ' / '.join(names)
            proposed.update(zotero_path=path(collections, proposed['zotero_root'], lambda r: r['key'], lambda r: r.get('parentCollection')),
                            tablet_path=path(folders, proposed['tablet_root'], lambda r: r.id, lambda r: r.parent), sync_paused=True)
            changed = not connections.same_roots(self.config, proposed)
            if changed:
                proposed = connections.switch(self.directory, self.config, proposed)
            excluded = connections.exclusions(self.directory, proposed)
            zscope = connections.filtered_scope(zscope, excluded['zotero'], lambda r: r['key'], lambda r: r.get('parentCollection'), proposed['zotero_root'])
            cscope = connections.filtered_scope(cscope, excluded['tablet'], lambda r: r.id, lambda r: r.parent, proposed['tablet_root'])
            if proposed.get('default_folder', proposed['tablet_root']) not in cscope:
                raise PilotError('That destination belongs to a paused folder connection. Choose another folder or use it as the new root.')
            retained = len(excluded['documents'])
            previous = next((row for row in self.config.get('connection_history', []) if connections.same_roots(row, proposed)), None)
            plan = {'proposed': proposed, 'changed': changed, 'old_tablet_path': self.config.get('tablet_path', 'Current reMarkable folder'),
                    'linked_papers': len(self.state.read('documents', {})), 'pending_reviews': len(self.review.rows()),
                    'paused_papers': retained, 'restored_papers': len(connections.values(self.directory, previous)['documents']) if previous else 0,
                    'zotero_folders': [row['name'] for row, depth in zscope.values() if depth],
                    'tablet_folders': [row.name for row, depth in cscope.values() if depth],
                    'excluded_zotero_folders': [r['name'] for r in collections if r['key'] in excluded['zotero']],
                    'excluded_tablet_folders': [r.name for r in folders if r.id in excluded['tablet']]}
            # UUIDs/timestamps used to stage a new connection are not part of the
            # confirmation. A fresh preview revalidates current metadata and state.
            stable = {k: v for k, v in proposed.items() if k not in {'connection_id', 'connection_history'}}
            plan['token'] = fingerprint({'state': self._connection_snapshot(), 'setup': stable, 'collections': collections,
                                         'folders': [(r.id, r.hash, r.name, r.parent) for r in folders],
                                         'exclusions': {k: sorted(v) for k, v in excluded.items()}})
            self.collections = collections
            return plan
        finally:
            client.close()

    def preview_connection(self, **values):
        self.pause_sync()
        return self._setup_plan(values)

    def configure(self, confirmation=None, **values):
        plan = self._setup_plan(values)
        if plan['changed'] and (self.config.get('tablet_root') or self.config.get('connection_history')):
            if confirmation != plan['token']:
                raise PilotError('Review the folder change again before saving. No folders or papers were changed.')
        proposed = plan['proposed']
        directory = connections.state_directory(self.directory, proposed)
        review, state = ReviewStore(directory / 'review'), BridgeState(directory / 'bridge')
        atomic_write(self.directory / 'config.json', json.dumps(proposed, ensure_ascii=False).encode())
        self.config, self.connection_dir, self.review, self.state = proposed, directory, review, state
        self.last = {'state': 'paused', 'message': 'Setup saved. Check your folders, then click Sync now when ready.'}
        return self.status()

    def preview_disconnect(self):
        self.pause_sync()
        return {'token': self._connection_snapshot(), 'linked_papers': len(self.state.read('documents', {})),
                'pending_reviews': len(self.review.rows())}

    def disconnect_folder(self, confirmation):
        if confirmation != self._connection_snapshot():
            raise PilotError('The connection changed. Review the disconnect again. Your files were retained.')
        proposed = connections.switch(self.directory, self.config, {**self.config, 'tablet_root': '', 'default_folder': '', 'tablet_path': ''})
        directory = connections.state_directory(self.directory, proposed)
        review, state = ReviewStore(directory / 'review'), BridgeState(directory / 'bridge')
        atomic_write(self.directory / 'config.json', json.dumps(proposed, ensure_ascii=False).encode())
        self.config, self.connection_dir, self.review, self.state = proposed, directory, review, state
        self.last = {'state': 'setup_required', 'message': 'Folder disconnected. Your papers and notes stay in Zotero and reMarkable.'}
        return self.status()

    def _proposal(self, path, metadata=None):
        from .sorting.core_logic import get_basic_document_details, build_proposed_filename, sanitize_filename_part, validate_document_filename
        details = get_basic_document_details(path)
        extracted_title = details.get('title', '')
        metadata = metadata or {}
        if metadata.get("title"):
            details["title"] = metadata["title"]
        reverse = {v: k for k, v in TYPE_MAP.items()}
        if metadata.get("itemType") in reverse:
            details["document_type"] = reverse[metadata["itemType"]]
        creators = metadata.get("creators", [])
        if creators:
            details["creators"] = [c.get("name") or " ".join(filter(None, [c.get("firstName"), c.get("lastName")])) for c in creators]
            details["primary_creator"] = details["creators"][0]
        if metadata.get("date"):
            details["year"] = metadata["date"][:4]
        template = self.config.get("templates", {}).get(details["document_type"], "")
        name = build_proposed_filename(details, path.suffix, filename_format="custom" if template else "smart", custom_template=template)
        if not template and (not details.get("year") or details.get("primary_creator", "").casefold() in {"", "unknown", "unknown author"}):
            name = path.name  # A readable paper does not need a perfect citation to keep a useful filename.
            if re.fullmatch(r'[0-9a-f]{64}', path.stem, re.I):
                # Cloud downloads use content hashes privately, never as the
                # visible tablet name when a readable name is available.
                readable = ''
                for candidate in (metadata.get('title'), extracted_title):
                    candidate = str(candidate or '').strip()
                    if candidate.lower().endswith(path.suffix.lower()):
                        candidate = candidate[:-len(path.suffix)].strip()
                    if candidate and not re.fullmatch(r'[0-9a-f]{64}', candidate, re.I):
                        readable = candidate
                        break
                if not readable:
                    readable = 'Paper'
                    details['filename_needs_review'] = True
                if re.fullmatch(r'[0-9a-f]{64}(?:\.pdf)?', str(details.get('title', '')), re.I):
                    details['title'] = readable
                stem = sanitize_filename_part(readable)[:220] or 'Paper'
                try:
                    name = validate_document_filename(stem + path.suffix, path.suffix)
                except ValueError:
                    name = validate_document_filename('Paper_' + stem + path.suffix, path.suffix)
        return {"details": details, "filename": name, "title": details.get("title", path.stem),
                "document_type": details["document_type"], "parent": metadata.get("key", "")}

    def _offer(self, kind, identity, path, *, metadata=None, **extra):
        from .inbox import _complete_document, file_signature
        if not self.review.observe_ready(kind + ":" + identity, file_signature(path)) or not _complete_document(path):
            return
        from .zotero_bulk import observed_digest
        digest = observed_digest(path, self.file_digests)
        old = next((r for r in self.review.rows(pending_only=False) if r["kind"] == kind and r["identity"] == identity), None)
        signature = citation_signature(metadata)
        if old and old["digest"] == digest and (old["status"] in {"approved", "applying"} or old["payload"].get("metadata_signature") == signature):
            return  # Do not re-extract every paper on every timer tick.
        payload = {**self._proposal(path, metadata), "path": str(path), "source": kind, "metadata_signature": signature, **extra}
        payload["review_token"] = fingerprint(payload)
        self.review.offer(kind, identity, digest, payload)

    def _native_pdf_matches(self, catalog):
        """Current, unmanaged originals only; cached review matches are not evidence."""
        from .zotero_bulk import observed_digest
        excluded = connections.exclusions(self.directory, self.config)
        managed = {row.get('source_key') for row in self.state.read('documents', {}).values()} | excluded['sources']
        indexed = {}
        for attachment in catalog['attachments']:
            if self.stop.is_set():
                raise InterruptedError('Sync stopped')
            record = attachment['data']
            if (Path(attachment['path']).suffix.lower() != '.pdf' or record['key'] in managed
                    or 'Notable pilot:' in record.get('note', '')):
                continue
            try:
                digest = observed_digest(attachment['path'], self.file_digests)
            except OSError:
                continue
            indexed.setdefault(digest, []).append({'key': record['key'], 'parent': record.get('parentItem', ''),
                'title': catalog['parents'].get(record.get('parentItem'), {}).get('title', Path(attachment['path']).stem)})
        return indexed

    @contextmanager
    def _catalog_paper(self, item):
        try:
            yield
        except (InterruptedError, AuthorizationRequired, TransportInterrupted):
            raise
        except (CloudError, PilotError, OSError, KeyError, ValueError) as error:
            if isinstance(error, CloudError) and 'authorization expired' in str(error).lower():
                raise
            if self.stop.is_set():
                raise InterruptedError('Sync stopped') from error
            self.catalog_issues.append({'cloud': item.id, 'title': item.name,
                                        'reason': f'Could not check this tablet paper: {error}'})

    def _catalog(self, client, cloud):
        self.catalog_issues = []
        native = client.review_action("catalog")
        documents = self.state.read("documents", {})
        excluded = connections.exclusions(self.directory, self.config)
        collections = client.collections()
        old_collections = set(excluded['zotero'])
        for _ in range(len(collections)):
            more = {row['key'] for row in collections if row.get('parentCollection') in old_collections}
            if more <= old_collections:
                break
            old_collections.update(more)
        active = descendants(collections, self.config['zotero_root'], lambda r: r['key'], lambda r: r.get('parentCollection'))
        active = connections.filtered_scope(active, excluded['zotero'], lambda r: r['key'], lambda r: r.get('parentCollection'), self.config['zotero_root'])
        managed_sources = {row.get("source_key") for row in documents.values()} | excluded['sources']
        for number, attachment in enumerate(native["attachments"], 1):
            if self.stop.is_set():
                raise InterruptedError('Sync stopped')
            record, path = attachment["data"], Path(attachment["path"])
            parent = native['parents'].get(record.get('parentItem'), {})
            homes = set(parent.get('collections', []))
            if homes & old_collections and not homes & set(active):
                continue
            if record["key"] in managed_sources or "Notable pilot:" in record.get("note", ""):
                continue
            self.progress(f'Checking Zotero file {number} of {len(native["attachments"])}: {path.name}')
            self._offer("zotero", record["key"], path, metadata=native["parents"].get(record.get("parentItem")), attachment=record["key"])
        inbox = self.config.get("inbox")
        if inbox:
            from .inbox import file_signature
            for path in Path(inbox).iterdir():
                if path.is_file() and path.suffix.lower() in {".pdf", ".docx", ".pptx"} and not path.name.startswith("~$"):
                    self._offer("inbox", str(path.resolve()) + "|" + fingerprint(file_signature(path))[:16], path)
        catalog = cloud.library()
        folders = [r for r in catalog if not r.deleted and r.kind == "CollectionType"]
        scope = descendants(folders, self.config["tablet_root"], lambda r: r.id, lambda r: r.parent)
        scope = connections.filtered_scope(scope, excluded['tablet'], lambda r: r.id, lambda r: r.parent, self.config['tablet_root'])
        candidates = []
        native_by_digest = None
        prior = {(row['kind'], row['identity']): row for row in self.review.rows(pending_only=False)}
        pending = [item for item in catalog if item.is_pdf and not item.deleted and item.parent in scope
                   and item.id not in documents and item.id not in excluded['documents']]
        for number, item in enumerate(pending, 1):
            if self.stop.is_set():
                raise InterruptedError('Sync stopped')
            self.progress(f'Checking tablet paper {number} of {len(pending)}: {item.name}')
            with self._catalog_paper(item):
                previous = prior.get(('cloud', item.id))
                path = Path(previous['payload'].get('path', '')) if previous else None
                from .zotero_bulk import observed_digest
                unchanged = (previous and previous['payload'].get('cloud_hash') == item.hash and path.is_file()
                             and observed_digest(path, self.file_digests) == previous['digest'])
                if unchanged:
                    digest = previous['digest']
                else:
                    bundle = cloud.pdf_bundle(item)
                    data = bundle[item.id + ".pdf"]
                    digest = hashlib.sha256(data).hexdigest()
                    path = self.connection_dir / "incoming" / (digest + ".pdf")
                    if not path.exists():
                        atomic_write(path, data, require_absent=True)
                    elif observed_digest(path, self.file_digests) != digest:
                        raise PilotError('A saved review PDF changed. It was retained; restore its original before retrying.')
                candidates.append({"key": item.id, "title": item.name, "digest": digest, "parent": item.parent, "side": "cloud"})
                old = self.review.approval("cloud", item.id, digest)
                repair = previous['payload'].get('repair_required', '') if previous and previous['status'] == 'pending' else ''
                if old is not None:
                    if native_by_digest is None:
                        native_by_digest = self._native_pdf_matches(native)
                    matches = native_by_digest.get(digest, [])
                    if any(match.get('parent') != old.get('parent') for match in matches):
                        repair = 'An identical PDF now exists in Zotero. Choose it before syncing to avoid a duplicate reference.'
                    elif Path(old.get('filename', '')).stem == digest:
                        repair = 'An earlier filing used a temporary download name. Check the readable name before syncing.'
                    if repair:
                        old = None
                if old is None:
                    if native_by_digest is None:
                        native_by_digest = self._native_pdf_matches(native)
                    readable_name = item.name
                    if item.name == digest and previous and previous['payload'].get('title') != digest:
                        readable_name = previous['payload'].get('title') or item.name
                    signature = fingerprint({'name': readable_name, 'templates': self.config.get('templates', {}), 'filename_policy': 2})
                    if previous and previous['digest'] == digest and previous['payload'].get('proposal_signature') == signature:
                        proposal = {key: previous['payload'][key] for key in ('details', 'filename', 'title', 'document_type', 'parent')}
                    else:
                        proposal = self._proposal(path, {"title": readable_name})
                    payload = {**proposal, "path": str(path), "source": "cloud", 'proposal_signature': signature,
                               "cloud": item.id, "cloud_hash": item.hash, "tablet_parent": item.parent}
                    # Byte-identical originals are strong match candidates. Titles
                    # and DOI alone never trigger annotation overlay or adoption.
                    payload["matches"] = native_by_digest.get(digest, [])
                    if repair:
                        payload.update(repair_required=repair, previous_approval=previous['payload'].get('previous_approval') or previous['approval'])
                    payload["review_token"] = fingerprint(payload)
                    if repair:
                        self.review.reopen(previous['id'], digest, payload)
                    self.review.offer("cloud", item.id, digest, payload)
        for row in self.review.rows():
            if row["kind"] in {"zotero", "inbox"} and row["payload"]["path"].lower().endswith(".pdf"):
                from .zotero_bulk import title_key
                name = title_key(Path(row["payload"]["path"]).stem)
                payload = {**row["payload"], "matches": [r for r in candidates if r["digest"] == row["digest"]],
                           "possible_tablet_matches": [r["title"] for r in candidates if r["digest"] != row["digest"]
                                                       and name == title_key(Path(r["title"]).stem)]}
                self.review.offer(row["kind"], row["identity"], row["digest"], payload)
        for identity, link in documents.items():
            item = next((r for r in catalog if r.id == identity), None)
            if self.review.link_control(identity)["paused"]:
                continue
            self.review.observe_live(item)
            if item and not item.deleted and link.get("parent"):
                parent = client.get("item", link["parent"])
                key = link.get("view_key") or link.get("source_key")
                view = client.get("item", key) if key else None
                self.review.confirm_zotero_deleted(item, link, parent if parent and parent.get("deleted") else view)
            if item and (item.deleted or item.parent == "trash") and link.get("parent"):
                published = self.state.directory / "publisher"
                from .zotero_pilot import Ledger
                namespace = Bridge(client, cloud, self.state, self.config["zotero_root"], self.config["tablet_root"]).namespace
                key = link.get("view_key") or stable_key(namespace, "attachment", identity)
                inventory = client.review_action("inventory", {"parent": link["parent"]})["inventory"]
                self.review.confirm_deleted(item, link, attachment=key, parent=link["parent"], inventory=inventory)
        return native

    def refresh_review_policy(self, client, catalog=None):
        from .zotero_bulk import review_policy
        rows = self.review.rows()
        catalog = catalog or client.review_action("catalog")
        native_matches = self._native_pdf_matches(catalog) if any(row['kind'] == 'cloud' and row['status'] == 'pending' for row in rows) else {}
        for row in rows:
            if row['kind'] == 'cloud' and row['status'] == 'pending':
                row['payload'] = {**row['payload'], 'matches': native_matches.get(row['digest'], [])}
        policy = review_policy(rows, catalog, self.state.read("documents", {}),
                               self.state.read("folders", {}), cancelled=self.stop.is_set, cache=self.file_digests)
        for row in rows:
            if row["status"] == "applying":
                continue  # Preserve the existing recovery journal.
            payload = {**row["payload"], "issues": policy[row["id"]], "routine": not policy[row["id"]]}
            payload["review_token"] = fingerprint({k: v for k, v in payload.items() if k != "review_token"})
            self.review.offer(row["kind"], row["identity"], row["digest"], payload)

    def scan_library(self, root, collection, lookup=True):
        return self.bulk.scan(root, collection, lookup)

    def import_library(self, plan_id):
        return self.bulk.apply(plan_id)

    def approve_routine(self, entries, collection):
        """One explicit batch decision, revalidated file by file, never blind approval."""
        if collection not in self.state.read("folders", {}):
            raise PilotError("Choose a mapped tablet destination in Setup first.")
        if not entries or len(entries) > 10000 or len({e["id"] for e in entries}) != len(entries):
            raise PilotError("Choose a current routine batch.")
        self.stop.clear()
        client = self.zotero()
        try:
            self.refresh_review_policy(client)
        except (InterruptedError, PilotError):
            if not self.stop.is_set():
                raise
            self.last = {'state': 'paused', 'message': f'Filing paused: 0 filed; {len(entries)} remaining.'}
            return self.status()
        finally:
            client.close()
        completed, held = 0, 0
        for number, expected in enumerate(entries, 1):
            if self.stop.is_set():
                break
            self.progress(f'Filing paper {number} of {len(entries)}…')
            row = self.review.row(expected["id"])
            if row and row["status"] == "approved":
                continue  # Linking one side can also resolve its identical counterpart's review.
            if (not row or row["status"] != "pending" or row["digest"] != expected["digest"]
                    or not row["payload"].get("routine") or row["payload"].get("review_token") != expected.get("review_token")):
                held += 1
                continue
            payload = row["payload"]
            matches = payload.get("matches", [])
            home = collection
            if row['kind'] == 'cloud' or len(matches) == 1:
                match_parent = payload.get('tablet_parent') if row['kind'] == 'cloud' else matches[0].get('parent')
                home = next((key for key, value in self.state.read("folders", {}).items() if value["cloud"] == match_parent), home)
            try:
                self.approve(row["id"], row["digest"], payload["filename"], payload["title"], payload["document_type"],
                             home, match=matches[0]["key"] if matches else "", review_token=payload["review_token"], _batch=True)
                completed += 1
            except InterruptedError:
                self.stop.set()
                break
            except Exception as error:
                if self.stop.is_set():
                    break
                payload = {**payload, "routine": False, "issues": [str(error)]}
                self.review.offer(row["kind"], row["identity"], row["digest"], payload)
                held += 1
        remaining = sum(1 for expected in entries if (self.review.row(expected['id']) or {}).get('status') != 'approved')
        self.last = {"state": "paused" if self.stop.is_set() else "needs_review" if held else "ready",
                     "message": f"Filing paused: {completed} filed; {remaining} remaining." if self.stop.is_set() else f"Filed {completed} papers together; {held} held for review. Sync transfers approved papers."}
        return self.status()

    def sync(self, automatic=False):
        if not self.config.get("tablet_root"):
            return self.status()
        if self.pause_pending.is_set():
            raise InterruptedError('Sync paused')
        if automatic and (self.config.get('sync_paused') or not self.config.get('automatic')):
            return self.status()
        if self.config.get('sync_paused'):
            self.config['sync_paused'] = False
            self.save()
        self._begin_operation()
        client = self.zotero(ocr=True)
        try:
            cloud = self.cloud()
            self.cleanup_intake(client)
            self.progress('Checking new papers and existing links…')
            self._catalog(client, cloud)
            self.refresh_review_policy(client)
            excluded = connections.exclusions(self.directory, self.config)
            excluded['documents'].update(issue['cloud'] for issue in self.catalog_issues if issue.get('cloud'))
            result = Bridge(client, cloud, self.state, self.config["zotero_root"], self.config["tablet_root"], review_policy=self.review, follow_changes=True,
                            progress=self.progress, exclusions=excluded).run(apply=True)
            catalog_failures = {row['cloud'] for row in self.catalog_issues}
            result['review'] = self.catalog_issues + [row for row in result['review'] if row.get('cloud') not in catalog_failures]
            self.collections = client.collections()
            self.last = {"state": "needs_review" if self.review.rows() or self.review.deletions() or self.review.local_deletions() or result["review"] else "ready",
                         "message": "Sync finished — some links need attention" if result["review"] else "Sync finished", "updated": time.time(), "result": result}
            return self.status()
        finally:
            client.close()

    def preview(self, identity, document_type, title, template=None):
        from .sorting.core_logic import build_proposed_filename, validate_filename_template
        row = self.review.row(identity)
        if not row:
            raise PilotError("Select a document in the review queue.")
        supplement = document_type == 'supporting_information'
        document_type = 'journal_article' if supplement else document_type
        details = {**row["payload"]["details"], "document_type": document_type, "title": title}
        if supplement:
            details['is_supplementary_material'] = True
        template = self.config.get("templates", {}).get(document_type, "") if template is None else template
        if template:
            validate_filename_template(template)
        return {"filename": build_proposed_filename(details, Path(row["payload"]["path"]).suffix,
                 filename_format="custom" if template else "smart", custom_template=template)}

    def approve(self, identity, digest, filename, title, document_type, collection, research=None, match="", review_token="", _batch=False,
                main_reference='', main_reference_metadata=None):
        from .sorting.core_logic import validate_document_filename
        row = self.review.row(identity)
        if not row or row["digest"] != digest:
            raise PilotError("The document changed. Refresh before approving.")
        if review_token and row["payload"].get("review_token") != review_token:
            raise PilotError("The reference details changed. Refresh the review before approving.")
        path = Path(row["payload"]["path"])
        client = self.zotero()
        try:
            if row['kind'] == 'cloud' and row['status'] == 'pending' and not _batch:
                # A PC import can add an identical original after this review
                # was displayed. Refresh locally and ask for a fresh choice.
                current_matches = self._native_pdf_matches(client.review_action('catalog')).get(digest, [])
                if current_matches != row['payload'].get('matches', []):
                    self.refresh_review_policy(client)
                    raise PilotError('The matching Zotero papers changed. Refresh the review and choose the current match before filing.')
            if row["kind"] == "zotero":
                path = client.file_path(row["identity"])
            filename = validate_document_filename(filename, path.suffix)
            if file_sha(path) != digest:
                raise PilotError("The file changed during review. Refresh it before filing.")
            collections = client.collections()
            mapped = descendants(collections, self.config["zotero_root"], lambda r: r["key"], lambda r: r.get("parentCollection"))
            if collection not in mapped or any(k not in {r["key"] for r in collections} for k in (research or [])):
                raise PilotError("Choose a current tablet home and current research collections.")
            parent = row["payload"].get("parent") or stable_key("notable-review", "reference", row["kind"] + row["identity"])
            source = row["identity"] if row["kind"] == "zotero" else stable_key("notable-review", "source", row["identity"])
            chosen_match = next((m for m in row["payload"].get("matches", []) if m["key"] == match), None)
            if match and not chosen_match:
                raise PilotError("Choose a displayed, byte-verified match or keep this document separate.")
            if row['kind'] == 'cloud':
                current = next((r for r in self.cloud().library() if r.id == row['identity']), None)
                # Recovery may have already renamed/moved this item itself.
                if (not current or current.deleted or (row['status'] != 'applying' and current.hash != row['payload'].get('cloud_hash'))):
                    raise PilotError('The tablet document changed since review. Sync to refresh it before filing.')
            if chosen_match and row["kind"] == "cloud":
                if file_sha(client.file_path(match)) != digest:
                    raise PilotError("The matching PDF changed. Its annotations were retained separately.")
                parent, source = chosen_match["parent"], match
                if not parent:
                    raise PilotError("Create a Zotero parent reference for this attachment before linking it.")
            elif chosen_match:
                matched_cloud = next((r for r in self.cloud().library() if r.id == match), None)
                if not matched_cloud or matched_cloud.deleted or hashlib.sha256(self.cloud().pdf_bundle(matched_cloud)[match + ".pdf"]).hexdigest() != digest:
                    raise PilotError("The tablet original changed. Refresh the match before linking.")
            supplement = (document_type == 'supporting_information' or row['payload'].get('details', {}).get('is_supplementary_material')
                          or re.search(r'(?:^|[_ -])si$', path.stem, re.I))
            source_parent = row['payload'].get('parent')
            source_reference = client.get('item', source_parent) if source_parent else None
            if supplement:
                if not main_reference:
                    raise PilotError('Choose the main paper in Zotero for this supporting information.')
                main = client.get('item', main_reference)
                if not main or main.get('deleted') or main.get('itemType') in {'attachment', 'annotation', 'note'}:
                    raise PilotError('The selected main paper is unavailable. Choose a current Zotero reference.')
                if not isinstance(main_reference_metadata, dict) or citation_signature(main) != citation_signature(main_reference_metadata):
                    raise PilotError('The main paper changed while this filing waited. Find and select it again.')
                if chosen_match and row['kind'] == 'cloud' and chosen_match.get('parent') != main_reference:
                    raise PilotError('The matching PDF belongs to a different reference. Check the main paper before linking.')
                parent = main_reference
            approval = {"filename": filename, "title": title, "document_type": document_type,
                        "parent": parent, "collection": collection, "source": source, "research": research or [], "match": match}
            reference = client.get("item", parent)
            if row["kind"] == "zotero" and source_parent and source_reference:
                if row["status"] != "applying" and row["payload"].get("metadata_signature") != citation_signature(source_reference):
                    raise PilotError("The Zotero citation changed during review. Sync to refresh it before filing.")
                if row["status"] == "applying" and source_reference.get("title") not in {row["payload"].get("title"), title}:
                    raise PilotError("The reference title changed while filing was interrupted. Review it before retrying.")
            self.review.begin(identity, digest, approval)
            if not reference:
                details = row["payload"]["details"]
                metadata = {"key": parent, "itemType": TYPE_MAP.get(document_type, "document"),
                            "title": title, "collections": sorted(set([collection, *(research or [])]))}
                creators = details.get("creators") or [details.get("primary_creator", "")]
                creator_type = "presenter" if document_type == "presentation_poster" else "inventor" if document_type in {"patent", "patent_application"} else "author"
                metadata["creators"] = [{"creatorType": creator_type, "name": str(name)} for name in creators if name and str(name).lower() not in {"unknown", "unknown author"}]
                year = str(details.get("year", ""))
                if len(year) == 4 and year.isdigit() and document_type not in {"patent", "patent_application"}:
                    metadata["date"] = year
                if document_type in {"journal_article", "preprint", "conference_paper", "book_chapter", "book", "thesis_dissertation", "technical_report"} and details.get("identifier", {}).get("doi"):
                    metadata["DOI"] = details["identifier"]["doi"]
                reference = client.create("item", metadata)
            else:
                reference["collections"] = sorted(set(reference.get("collections", []) + [collection] + (research or [])))
                if not supplement and not (chosen_match and row['kind'] == 'cloud'):
                    reference["title"] = title
                # Bibliographic metadata already curated in Zotero is retained;
                # edits to it remain available through Zotero's native item pane.
                client.update(reference)
            self.apply_document_keywords(client, parent, path, identity, digest)
            if row["kind"] == "inbox":
                from .inbox import file_signature
                self.review.cleanup(identity, {"source": str(path), "signature": file_signature(path), "sha256": digest, "target": source})
                attachment = client.get("item", source)
                if not attachment:
                    client.create("item", {"key": source, "itemType": "attachment", "parentItem": parent,
                        "linkMode": "imported_file", "contentType": mimetypes.guess_type(filename)[0] or "application/octet-stream",
                        "title": filename, "filename": filename})
                current = client.file_md5(source)
                wanted = hashlib.md5(path.read_bytes()).hexdigest()
                if current not in {"", wanted}:
                    raise PilotError("A previously imported attachment changed. Both files were retained.")
                if current != wanted:
                    client.upload(source, path, current)
                if client.file_md5(source) != wanted:
                    raise PilotError("Import verification failed. The download was retained.")
                # Gate the newly stored attachment under its Zotero identity too.
                zreview = self.review.offer("zotero", source, digest, row["payload"])
                self.review.begin(zreview, digest, approval)
                self.review.finish(zreview)
            elif row["kind"] == "zotero":
                attachment = client.get("item", source)
                if not attachment.get("parentItem") or (supplement and attachment.get('parentItem') != parent):
                    attachment["parentItem"] = parent
                    attachment.pop("collections", None)
                    client.update(attachment)
                client.review_action("rename", {"key": source, "filename": filename, "md5": hashlib.md5(path.read_bytes()).hexdigest()})
            if row["kind"] == "cloud" or chosen_match:
                cloud = self.cloud()
                cloud_identity = row["identity"] if row["kind"] == "cloud" else match
                item = next((r for r in cloud.library() if r.id == cloud_identity), None)
                if not item or item.deleted:
                    raise PilotError("The tablet document moved or was trashed. Refresh the review.")
                folders = self.state.read("folders", {})
                if collection not in folders:
                    raise PilotError("Sync the selected tablet home before filing.")
                destination = folders[collection]["cloud"]
                cloud.update_item(item.id, expected_hash=item.hash, name=Path(filename).stem, parent=destination, scope_id=self.config["tablet_root"])
                if chosen_match:
                    links = self.state.read("documents", {})
                    links[item.id] = {"origin": "zotero", "source_key": source, "parent": parent, "collection": collection,
                        "baseline": digest, "uploaded": True, "name": Path(filename).stem, "tablet_parent": destination}
                    self.state.write("documents", links)
                    original = self.state.directory / "originals" / (digest + ".pdf")
                    if not original.exists():
                        atomic_write(original, path.read_bytes(), require_absent=True)
                    zreview = self.review.offer("zotero", source, digest, row["payload"])
                    self.review.begin(zreview, digest, approval)
                    self.review.finish(zreview)
                    pending_cloud = next((r for r in self.review.rows() if r["kind"] == "cloud" and r["identity"] == item.id), None)
                    if pending_cloud:
                        self.review.begin(pending_cloud["id"], pending_cloud["digest"], approval)
                        self.review.finish(pending_cloud["id"])
            self.review.finish(identity, approval=approval)
            if row["kind"] == "cloud" or chosen_match:
                self.review.link_control(item.id, event={"action": "linked" if chosen_match else "approved", "filename": filename})
            if row["kind"] == "inbox":
                self.cleanup_intake(client)
            return {} if _batch else self.status()
        finally:
            client.close()

    def cleanup_intake(self, client):
        from .inbox import _finish_verified_copy
        for job in self.review.cleanups():
            row = self.review.row(job["identity"])
            if not row or row["status"] != "approved":
                continue
            data = job["payload"]
            source = Path(data["source"])
            if not source.exists():
                self.review.cleanup(job["identity"], complete=True)
                continue
            try:
                _finish_verified_copy(source, client.file_path(data["target"]), data["signature"], data["sha256"])
                self.review.cleanup(job["identity"], complete=True)
            except (OSError, ValueError):
                # A locked or changed download is retained; the verified import
                # and its recorded cleanup can be retried on a later cycle.
                continue

    def delete_decision(self, identity, choice):
        client = self.zotero()
        try:
            result = self.review.resolve_deletion(identity, choice, cloud=self.cloud(), zotero=client, scope=self.config["tablet_root"])
            return {"decision": result, **self.status()}
        finally:
            client.close()

    def link(self, identity, paused):
        links = self.state.read("documents", {})
        row = links.get(identity)
        if not row:
            raise PilotError("This recorded paper link is unavailable.")
        if not paused:
            item = next((r for r in self.cloud().library() if r.id == identity), None)
            if not item or item.deleted or hashlib.sha256(self.cloud().pdf_bundle(item)[identity + ".pdf"]).hexdigest() != row["baseline"]:
                raise PilotError("The tablet original changed. Match its edition again before resuming.")
            client = self.zotero()
            try:
                parent = client.get("item", row["parent"])
                view = client.get("item", row.get("view_key") or row.get("source_key"))
                if not parent or parent.get("deleted") or not view or view.get("deleted"):
                    raise PilotError("Restore the Zotero paper before resuming this link.")
            finally:
                client.close()
        self.review.link_control(identity, paused=paused, event={"action": "unlinked" if paused else "resumed"})
        return self.status()

    def local_delete_decision(self, identity, choice):
        client = self.zotero()
        try:
            self.review.resolve_local_deletion(identity, choice, cloud=self.cloud(), zotero=client, scope=self.config["tablet_root"])
            return self.status()
        finally:
            client.close()

    def move_link(self, identity, name, collection, revision):
        from .sorting.core_logic import validate_document_filename
        name = Path(validate_document_filename(name, ".pdf")).stem
        links = self.state.read("documents", {})
        row = links.get(identity)
        maps = self.state.read("folders", {})
        if not row or collection not in maps or row.get("revision") != revision:
            raise PilotError("The selected link changed. Sync before renaming or moving it.")
        item = next((r for r in self.cloud().library() if r.id == identity), None)
        if not item or item.deleted or item.hash != revision:
            raise PilotError("The tablet copy changed. Sync before renaming or moving it.")
        client = self.zotero()
        try:
            path = client.file_path(row["view_key"])
            if path.stem != row.get("desktop_name"):
                raise PilotError("The desktop filename changed. Sync before editing this link.")
            Bridge(client, self.cloud(), self.state, self.config["zotero_root"], self.config["tablet_root"]).set_desktop_document(row, name, collection, maps)
            self.review.link_control(identity, event={"action": "rename or move requested", "name": name})
            return self.status()
        finally:
            client.close()

    def reindex(self, key):
        if key not in {r.get("view_key") for r in self.state.read("documents", {}).values()}:
            raise PilotError("Select a linked PDF to rebuild its search index.")
        # Local search remains usable while tablet transfers are paused. A new
        # pause/cancel request can still interrupt this independent operation.
        self._begin_operation()
        client = self.zotero(ocr=True)
        try:
            path = client.file_path(key)
            before = file_sha(path)
            missing = client.index(key, path)
            if file_sha(path) != before:
                raise PilotError("The PDF changed while indexing. Refresh its link.")
            return {"pages_without_text": missing, **self.status()}
        finally:
            client.close()

    def tag_context(self, key, page=None):
        from .zotero_tags import names
        links = self.state.read('documents', {})
        matches = [(identity, row) for identity, row in links.items() if row.get('view_key') == key]
        if len(matches) != 1:
            raise PilotError('Sync and link this PDF before adding page tags.')
        identity, row = matches[0]
        if not row.get('page_map') or not row.get('page_map_digest'):
            raise PilotError('Sync this PDF to load its stable page identities.')
        client = self.zotero()
        try:
            if file_sha(client.file_path(key)) != row['page_map_digest']:
                raise PilotError('This PDF changed. Sync before editing its page tags.')
            parent = client.get('item', row['parent'])
            if not parent or parent.get('deleted'):
                raise PilotError('This reference is unavailable.')
            if page is not None and (type(page) is not int or not 0 <= page < len(row['page_map'])):
                raise PilotError('Choose an available PDF page.')
            pid = row['page_map'][page] if page is not None else None
            vocabulary = {v['tag'] for v in parent.get('tags', [])}
            for link in links.values():
                vocabulary.update(link.get('tag_state', {}).get('paper', []))
                for values in link.get('page_tags', {}).values():
                    vocabulary.update(values)
            context = {'key': key, 'cloud': identity, 'title': parent.get('title', row['name']),
                       'paper_tags': [v['tag'] for v in parent.get('tags', [])],
                       'page': page, 'page_id': pid, 'page_tags': row.get('page_tags', {}).get(pid, []),
                       'vocabulary': sorted(vocabulary), 'version': parent.get('version', 0),
                       'interrupted': bool(row.get('tag_pending')),
                       'orphaned_pages': {pid: values for pid, values in row.get('page_tags', {}).items()
                                          if pid not in row['page_map'] and values}}
            context['token'] = fingerprint(context)
            return context
        finally:
            client.close()

    def combine_tag_copies(self, key, page, token):
        """Explicit recovery: union the two current copies, keeping all labels."""
        from .zotero_tags import tablet_tags
        context = self.tag_context(key, page)
        if context['token'] != token:
            raise PilotError('The current tags changed. Reopen the page editor first.')
        links = self.state.read('documents', {})
        row = links[context['cloud']]
        cloud = self.cloud()
        item = next((r for r in cloud.library() if r.id == context['cloud']), None)
        if not item or item.deleted:
            raise PilotError('This tablet PDF is unavailable. Its tags were retained.')
        paper, remote_pages = tablet_tags(json.loads(cloud.pdf_bundle(item)[item.id + '.content']))
        local = row.get('page_tags', {})
        row['page_tags'] = {pid: sorted(set(local.get(pid, [])) | set(remote_pages.get(pid, [])))
                            for pid in set(local) | set(remote_pages)}
        client = self.zotero()
        try:
            parent = client.get('item', row['parent'])
            existing = {t['tag']: t for t in parent.get('tags', [])}
            parent['tags'] = [existing.get(t, {'tag': t}) for t in sorted(set(existing) | paper)]
            client.authorize()
            client.update(parent)
        finally:
            client.close()
        row.pop('tag_state', None)
        row.pop('tag_pending', None)
        row.pop('seen_tags', None)
        self.state.write('documents', links)
        return self.tag_context(key, page)

    def remove_unavailable_page_tags(self, key, page, page_id, token):
        context = self.tag_context(key, page)
        if context['token'] != token or page_id not in context['orphaned_pages']:
            raise PilotError('This page-tag review changed. Reopen the page editor first.')
        links = self.state.read('documents', {})
        links[context['cloud']]['page_tags'].pop(page_id)
        self.state.write('documents', links)
        return self.tag_context(key, page)

    def set_page_tags(self, key, page, page_id, tags, token, paper_tags=None):
        from .zotero_tags import names
        tags = names(tags)
        context = self.tag_context(key, page)
        if context['token'] != token or context['page_id'] != page_id:
            raise PilotError('These page tags changed. Reopen Tag this page before saving.')
        if paper_tags is not None:
            paper_tags = names(paper_tags)
            client = self.zotero()
            try:
                parent = client.get('item', self.state.read('documents', {})[context['cloud']]['parent'])
                if parent.get('version', 0) != context['version']:
                    raise PilotError('The paper tags changed. Reopen Tag this page before saving.')
                old = {v['tag']: v for v in parent.get('tags', [])}
                if set(paper_tags) != set(old):
                    parent['tags'] = [old.get(t, {'tag': t}) for t in paper_tags]
                    client.authorize()
                    client.update(parent)
            finally:
                client.close()
        links = self.state.read('documents', {})
        row = links[context['cloud']]
        row.setdefault('page_tags', {})[page_id] = tags
        self.state.write('documents', links)
        return self.tag_context(key, page)

    def tag_search(self, query='', scope='both'):
        if scope not in {'both', 'paper', 'page'} or not isinstance(query, str):
            raise PilotError('Choose paper tags, page tags, or both.')
        query = query.strip().casefold()
        client = self.zotero()
        results, vocabulary = [], set()
        try:
            catalog = client.review_action('catalog')
            parents = catalog['parents']
            attachments = {}
            for a in catalog['attachments']:
                if Path(a['path']).suffix.lower() == '.pdf':
                    attachments.setdefault(a['data'].get('parentItem'), []).append(a['data']['key'])
            for key, parent in parents.items():
                tags = [v['tag'] for v in parent.get('tags', [])]
                vocabulary.update(tags)
                matched = [t for t in tags if not query or query in t.casefold()]
                if scope != 'page' and matched:
                    results.append({'scope': 'paper', 'parent': key, 'key': next(iter(attachments.get(key, [])), ''),
                                    'title': parent.get('title', ''), 'tags': matched})
            for identity, row in self.state.read('documents', {}).items():
                parent = parents.get(row.get('parent'))
                if not parent or row.get('view_key') not in attachments.get(row.get('parent'), []):
                    continue
                for number, pid in enumerate(row.get('page_map', [])):
                    tags = row.get('page_tags', {}).get(pid, [])
                    vocabulary.update(tags)
                    matched = [t for t in tags if not query or query in t.casefold()]
                    if scope != 'paper' and matched:
                        results.append({'scope': 'page', 'parent': row['parent'], 'key': row['view_key'],
                                        'cloud': identity, 'page_id': pid, 'page': number,
                                        'title': parent.get('title', row['name']), 'tags': matched})
            return {'results': results, 'vocabulary': sorted(vocabulary)}
        finally:
            client.close()

    def resolve_conflict(self, identity, digest, side):
        row = self.review.row(identity)
        if not row or row["kind"] != "conflict" or row["digest"] != digest or side not in {"desktop", "tablet"}:
            raise PilotError("This mapping review changed. Refresh before deciding.")
        client = self.zotero()
        try:
            payload = row["payload"]
            paper = payload["type"] == "paper"
            record = client.get("item" if paper else "collection", payload["zotero"])
            item = next((r for r in self.cloud().library() if r.id == payload["cloud"]), None)
            if not record or not item or item.hash != payload["cloud_hash"] or record.get("version", 0) != payload["version"]:
                raise PilotError("The folder changed since review. Sync again before choosing.")
            if not paper and [record["name"], record.get("parentCollection")] != payload["desktop"]:
                raise PilotError("The folder changed since review. Sync again before choosing.")
            links = self.state.read("documents", {})
            link = links.get(payload["cloud"]) if paper else None
            if paper:
                path = client.file_path(link.get("view_key") or link.get("source_key"))
                if hashlib.md5(path.read_bytes()).hexdigest() != payload["file_md5"]:
                    raise PilotError("The PDF changed during review. Sync before choosing.")
            self.review.begin(identity, digest, {"side": side})
            chosen = payload[side]
            if side == "desktop":
                mappings = self.state.read("folders", {})
                self.cloud().update_item(item.id, expected_hash=item.hash, name=chosen[0], parent=mappings[chosen[1]]["cloud"], scope_id=self.config["tablet_root"])
            else:
                if paper:
                    Bridge(client, self.cloud(), self.state, self.config["zotero_root"], self.config["tablet_root"]).set_desktop_document(link, chosen[0], chosen[1], self.state.read("folders", {}))
                else:
                    record["name"], record["parentCollection"] = chosen
                    client.update_collection(record)
            if paper:
                mappings = self.state.read("folders", {})
                link.update(name=chosen[0], desktop_name=chosen[0], collection=chosen[1], tablet_parent=mappings[chosen[1]]["cloud"])
                self.state.write("documents", links)
            self.review.finish(identity)
            return self.status()
        finally:
            client.close()

    def dispatch(self, method, params):
        allowed = {"status", "connect", "pair", "folders", "configure", "preview_connection", "preview_disconnect", "disconnect_folder", "pause_sync", "sync", "preview", "approve", "delete_decision", "resolve_conflict", "link", "reindex", "local_delete_decision", "move_link", "scan_library", "import_library", "approve_routine", "tag_context", "set_page_tags", "tag_search", "combine_tag_copies", "remove_unavailable_page_tags"}
        allowed.update({'paper_tag_candidates', 'suggest_paper_tags', 'save_paper_tags'})
        if method not in allowed:
            raise PilotError("Unsupported plugin request.")
        if method not in {'status', 'pause_sync', 'preview_disconnect'}:
            self._begin_operation()
        return getattr(self, method)(**params)


def main(argv=None, *, worker_factory=Worker):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--port", type=int, default=23119)
    parser.add_argument("--debug-stacks", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    # Gecko sends UTF-8 JSON. The console code page must not reinterpret titles,
    # user-entered tags or filenames arriving through the private stdin pipe.
    if hasattr(sys.stdin, 'reconfigure'):
        sys.stdin.reconfigure(encoding='utf-8')
    debug_stream = None
    if args.debug_stacks:
        import faulthandler
        args.state.mkdir(parents=True, exist_ok=True)
        debug_stream = (args.state / "test-worker-stack.log").open("w", encoding="utf-8")
        faulthandler.dump_traceback_later(20, repeat=True, file=debug_stream)
    resources = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    worker = worker_factory(args.state, args.port, resources=resources)
    # NumPy/OpenBLAS's Windows DLL initialization inspects piped stdin. A
    # concurrent blocking stdin reader can deadlock that native import. Load
    # NumPy on the main thread before starting the transport reader, including
    # when handwriting recognition will only be requested later in the session.
    # Upstream: numpy/numpy#24290; modelcontextprotocol/python-sdk#2832.
    if sys.platform == "win32":
        import numpy  # noqa: F401
    pending = queue.Queue()
    def read():
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if request.get("method") in {"cancel", "shutdown", "pause_sync"}:
                    worker.stop.set()
                    if request["method"] == "shutdown":
                        break
                    if request['method'] == 'pause_sync':
                        try:
                            atomic_write(worker.directory / 'pause-requested.json', b'{}')
                        except OSError:
                            pass  # The queued pause reports a failed config save to the UI.
                        worker.pause_pending.set()
                        pending.put(request)
                else:
                    pending.put(request)
            except (ValueError, TypeError):
                pass
        worker.stop.set()
        pending.put(None)
    threading.Thread(target=read, daemon=True).start()
    logging.disable(logging.CRITICAL)
    transport = sys.stdout
    last_links = None
    def progress(message):
        nonlocal last_links
        packet = {'event': 'progress', 'message': message}
        links = progress_links(worker)
        if links is not None:
            signature = json.dumps(links, sort_keys=True)
            if signature != last_links:
                packet['links'] = links
                last_links = signature
        write_packet(transport, packet)
    worker.progress = progress
    while True:
        request = pending.get()
        if request is None:
            break
        response = {"id": request.get("id")}
        try:
            # Third-party diagnostic output must never corrupt the JSON stream.
            with redirect_stdout(sys.stderr):
                response["result"] = worker.dispatch(request.get("method"), request.get("params", {}))
        except Exception as error:
            if isinstance(error, InterruptedError):
                worker.last = {"state": "paused", "message": "Sync stopped. Your files and pending reviews were retained."}
                response["result"] = worker.status()
                write_packet(transport, response)
                continue
            safe = str(error) if isinstance(error, (PilotError, CloudError, ValueError, FileNotFoundError)) else "The operation could not finish. Your files were retained; retry from Notable."
            worker.last = {"state": "needs_attention", "message": safe, "error": type(error).__name__}
            response["error"] = {"message": safe, "type": type(error).__name__}
        write_packet(transport, response)


if __name__ == "__main__":
    main()
