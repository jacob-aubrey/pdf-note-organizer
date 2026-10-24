"""Durable user review and confirmed-deletion decisions for the Zotero UI.

No cloud calls, UI framework, account secrets or library writes occur merely
by importing this module. Actions use existing adapters and stable identities.
"""
import hashlib
import json
from pathlib import Path
import time

from .zotero_pilot import Ledger, PilotError, ReviewChanged


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class ReviewStore(Ledger):
    def __init__(self, directory):
        super().__init__(directory)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS review_queue (id TEXT PRIMARY KEY, kind TEXT NOT NULL, identity TEXT NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, approval TEXT NOT NULL DEFAULT '{}', UNIQUE(kind,identity))")
            db.execute("CREATE TABLE IF NOT EXISTS deletion_decisions (id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL, action TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT '{}')")
            db.execute("CREATE TABLE IF NOT EXISTS observations (identity TEXT PRIMARY KEY, signature TEXT NOT NULL, first_seen REAL NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS link_controls (identity TEXT PRIMARY KEY, paused INTEGER NOT NULL, history TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS local_deletions (id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL, action TEXT NOT NULL DEFAULT '')")
            db.execute("CREATE TABLE IF NOT EXISTS intake_cleanup (identity TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL)")

    def cleanup(self, identity, payload=None, *, complete=False):
        with self.connect() as db:
            if payload is not None:
                db.execute("INSERT OR IGNORE INTO intake_cleanup VALUES(?,?,'pending')", (identity, json.dumps(payload)))
            if complete:
                db.execute("UPDATE intake_cleanup SET status='complete' WHERE identity=?", (identity,))

    def cleanups(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM intake_cleanup WHERE status='pending'").fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def confirm_zotero_deleted(self, item, link, record):
        if not item or item.deleted or not record or not record.get("deleted"):
            return
        key = fingerprint(["zotero-trash", item.id, item.hash, record["key"]])[:24]
        payload = {"cloud": item.id, "cloud_hash": item.hash, "title": link["name"], "key": record["key"]}
        with self.connect() as db:
            for old in db.execute("SELECT id,payload FROM local_deletions WHERE status!='resolved' AND id!=?", (key,)).fetchall():
                if json.loads(old["payload"])["cloud"] == item.id:
                    db.execute("UPDATE local_deletions SET status='resolved',action='superseded' WHERE id=?", (old["id"],))
            db.execute("INSERT OR IGNORE INTO local_deletions VALUES(?,?,'pending','')", (key, json.dumps(payload)))

    def observe_live(self, item):
        if not item or item.deleted or item.parent == "trash":
            return
        with self.connect() as db:
            for row in db.execute("SELECT id,payload,status,action FROM deletion_decisions WHERE status!='resolved'").fetchall():
                if json.loads(row["payload"])["cloud"] == item.id and (row["status"] == "pending" or row["action"] == "restore"):
                    db.execute("UPDATE deletion_decisions SET status='resolved',action='restore',result=? WHERE id=?",
                               (json.dumps({"action": "restore", "external": True, "cloud": item.id}), row["id"]))

    def local_deletions(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM local_deletions WHERE status!='resolved' ORDER BY rowid").fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def resolve_local_deletion(self, identity, choice, *, cloud, zotero, scope):
        if choice not in {"trash_tablet", "keep_tablet"}:
            raise PilotError("Choose whether to keep the tablet copy or send it to Trash.")
        row = next((r for r in self.local_deletions() if r["id"] == identity), None)
        if not row:
            raise PilotError("This deletion decision is no longer pending.")
        data = row["payload"]
        record = zotero.get("item", data["key"])
        item = next((r for r in cloud.library() if r.id == data["cloud"]), None)
        if not record or not record.get("deleted") or not item:
            raise PilotError("The linked item changed. Sync again before deciding.")
        if not item.deleted and item.hash != data["cloud_hash"]:
            raise PilotError("The tablet copy changed after this notification. Sync before deciding.")
        if choice == "trash_tablet" and not item.deleted:
            cloud.update_item(item.id, expected_hash=item.hash, parent="trash", scope_id=scope)
        self.link_control(item.id, paused=True, event={"action": choice})
        with self.connect() as db:
            db.execute("UPDATE local_deletions SET status='resolved',action=? WHERE id=?", (choice, identity))

    def link_control(self, identity, *, paused=None, event=None):
        with self.connect() as db:
            row = db.execute("SELECT paused,history FROM link_controls WHERE identity=?", (identity,)).fetchone()
            value = {"paused": bool(row[0]) if row else False, "history": json.loads(row[1]) if row else []}
            if paused is not None:
                value["paused"] = bool(paused)
            if event:
                value["history"].append({"time": time.time(), **event})
            if paused is not None or event:
                db.execute("INSERT OR REPLACE INTO link_controls VALUES(?,?,?)", (identity, int(value["paused"]), json.dumps(value["history"])))
        return value

    def observe_ready(self, identity, signature, *, now=None, settle=2):
        now = time.time() if now is None else now
        with self.connect() as db:
            row = db.execute("SELECT signature,first_seen FROM observations WHERE identity=?", (identity,)).fetchone()
            if row and row[0] == signature:
                return now - row[1] >= settle
            db.execute("INSERT OR REPLACE INTO observations VALUES(?,?,?)", (identity, signature, now))
        return False

    def offer(self, kind, identity, digest, payload):
        key = fingerprint([kind, identity])[:24]
        with self.connect() as db:
            old = db.execute("SELECT digest,status,approval FROM review_queue WHERE id=?", (key,)).fetchone()
            if old and old[0] == digest and old[1] in {"approved", "ignored"}:
                return key
            # Keep an explicitly approved action journal during recovery. A
            # changed input gets a new pending review instead of stale consent.
            db.execute("INSERT INTO review_queue(id,kind,identity,digest,payload,status) VALUES(?,?,?,?,?,'pending') ON CONFLICT(id) DO UPDATE SET digest=excluded.digest,payload=excluded.payload,status=CASE WHEN review_queue.digest=excluded.digest AND review_queue.status='applying' THEN 'applying' ELSE 'pending' END,approval=CASE WHEN review_queue.digest=excluded.digest THEN review_queue.approval ELSE '{}' END",
                       (key, kind, identity, digest, json.dumps(payload)))
        return key

    def rows(self, *, pending_only=True):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM review_queue" + (" WHERE status IN ('pending','applying')" if pending_only else "") + " ORDER BY rowid").fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"]), "approval": json.loads(row["approval"])} for row in rows]

    def reopen(self, identity, expected_digest, payload):
        """Hold an approved, unpublished action when new evidence makes it unsafe."""
        with self.connect() as db:
            db.execute("UPDATE review_queue SET status='pending',payload=?,approval='{}' WHERE id=? AND digest=? AND status='approved'",
                       (json.dumps(payload), identity, expected_digest))

    def row(self, identity):
        with self.connect() as db:
            row = db.execute("SELECT * FROM review_queue WHERE id=?", (identity,)).fetchone()
        return {**dict(row), "payload": json.loads(row["payload"]), "approval": json.loads(row["approval"])} if row else None

    def begin(self, identity, expected_digest, approval):
        with self.connect() as db:
            row = db.execute("SELECT digest,status FROM review_queue WHERE id=?", (identity,)).fetchone()
            if not row or row[0] != expected_digest or row[1] not in {"pending", "applying"}:
                raise PilotError("This review changed. Refresh it before approving.")
            db.execute("UPDATE review_queue SET status='applying',approval=? WHERE id=?", (json.dumps(approval), identity))

    def finish(self, identity, *, approval=None):
        with self.connect() as db:
            if approval is not None:
                db.execute("UPDATE review_queue SET approval=? WHERE id=?", (json.dumps(approval), identity))
            db.execute("UPDATE review_queue SET status='approved' WHERE id=? AND status='applying'", (identity,))

    def approval(self, kind, identity, digest):
        with self.connect() as db:
            row = db.execute("SELECT digest,status,approval FROM review_queue WHERE kind=? AND identity=?", (kind, identity)).fetchone()
        if row and row[0] == digest and row[1] == "approved":
            return json.loads(row[2])
        return None

    def primary_collection(self, parent):
        for row in self.rows(pending_only=False):
            if row["status"] == "approved" and row["approval"].get("parent") == parent:
                return row["approval"].get("collection")
        return None

    def confirm_deleted(self, cloud_item, link, *, attachment, parent, inventory):
        if not cloud_item or not (cloud_item.deleted or cloud_item.parent == "trash"):
            return None  # Missing IDs and unreachable cloud are not deletion proof.
        key = fingerprint(["tablet-trash", cloud_item.id, cloud_item.hash])[:24]
        payload = {"cloud": cloud_item.id, "cloud_hash": cloud_item.hash, "title": link["name"],
                   "restore_parent": link.get("tablet_parent"), "attachment": attachment,
                   "source_attachment": link.get("source_key", "") if link.get("source_key") != attachment else "", "parent": parent,
                   "inventory": inventory}
        with self.connect() as db:
            for old in db.execute("SELECT id,payload FROM deletion_decisions WHERE status!='resolved' AND id!=?", (key,)).fetchall():
                if json.loads(old["payload"])["cloud"] == cloud_item.id:
                    db.execute("UPDATE deletion_decisions SET status='resolved',action='superseded',result=? WHERE id=?", (json.dumps({"reason": "Newer tablet trash revision"}), old["id"]))
            db.execute("INSERT OR IGNORE INTO deletion_decisions VALUES(?,?,'pending','','{}')", (key, json.dumps(payload)))
            db.execute("UPDATE deletion_decisions SET payload=? WHERE id=? AND status='pending'", (json.dumps(payload), key))
        return key

    def deletions(self, *, pending_only=True):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM deletion_decisions" + (" WHERE status!='resolved'" if pending_only else "") + " ORDER BY rowid").fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"]), "result": json.loads(row["result"])} for row in rows]

    def resolve_deletion(self, identity, action, *, cloud, zotero, scope):
        if action not in {"restore", "pdf_only", "everything"}:
            raise PilotError("Choose Restore, Delete PDF only, or Delete everything.")
        with self.lock():
            row = next((row for row in self.deletions(pending_only=False) if row["id"] == identity), None)
            if not row:
                raise PilotError("This deletion notification is unavailable.")
            if row["status"] == "resolved":
                if row["action"] != action:
                    raise PilotError("This deletion already has a different recorded decision.")
                return row["result"]
            if row["action"] and row["action"] != action:
                raise PilotError("A different deletion action is being recovered. Refresh its status.")
            data = row["payload"]
            item = next((r for r in cloud.library() if r.id == data["cloud"]), None)
            # Recognize an interrupted, already-completed restore by its recorded
            # destination. Other newer cloud edits require a fresh decision.
            restored = action == "restore" and row["status"] == "applying" and item and not item.deleted and item.parent == data["restore_parent"]
            if not restored and (not item or item.hash != data["cloud_hash"] or not (item.deleted or item.parent == "trash")):
                raise PilotError("The tablet item changed since this notification. Refresh before deciding.")
            with self.connect() as db:
                db.execute("UPDATE deletion_decisions SET status='applying',action=? WHERE id=?", (action, identity))
            if action == "restore":
                if not data["restore_parent"]:
                    raise PilotError("Choose a live destination before restoring this paper.")
                if not restored:
                    cloud.update_item(item.id, expected_hash=item.hash, parent=data["restore_parent"], scope_id=scope, restore=True)
            else:
                # The native Zotero endpoint validates the whole displayed
                # attachment/note inventory again inside its transaction. It
                # uses Zotero Trash and never permanently erases records.
                try:
                    zotero.review_action("trash", {"choice": action, **data})
                except ReviewChanged:
                    with self.connect() as db:
                        db.execute("UPDATE deletion_decisions SET status='pending',action='' WHERE id=?", (identity,))
                    raise
            result = {"action": action, "cloud": data["cloud"], "parent": data["parent"],
                      "attachment": data["attachment"], "status": "resolved"}
            with self.connect() as db:
                db.execute("UPDATE deletion_decisions SET status='resolved',result=? WHERE id=?", (json.dumps(result), identity))
            return result

    def suspended_documents(self):
        # A confirmed deletion remains suspended even after a local-trash
        # choice; only an explicit restore resumes its link.
        result = set()
        for row in self.deletions(pending_only=False):
            if row["status"] != "resolved" or row["action"] != "restore":
                result.add(row["payload"]["cloud"])
            elif row["action"] == "restore":
                result.discard(row["payload"]["cloud"])
        result.update(row["payload"]["cloud"] for row in self.local_deletions())
        with self.connect() as db:
            result.update(row[0] for row in db.execute("SELECT identity FROM link_controls WHERE paused=1"))
        return result
