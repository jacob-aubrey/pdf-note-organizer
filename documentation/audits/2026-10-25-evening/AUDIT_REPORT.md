# Evening full plugin audit — October 25, 2026

Status: in progress. Source and package reconciliation found that installed 0.8.7 omitted committed transport fixes. Version 0.8.8 is installed and the configured production sync started at 22:51:08 UTC; repeat-sync verification follows.

The evening run began at 22:30 UTC (6:30 p.m. America/New_York). The starting revision is `7bdb3a63bf198692883286749693fca9cabcb78d`, initially with a clean working tree. The earlier October 25 audit began at `d84f9516f4ed8b0623e37c3ecdf254cd386687c0`; its local edits were subsequently included in the existing 0.8.7 release commit. This audit did not create that commit or publish a release. New changes here are the 0.8.8 manifest/version note and audit evidence.

## New findings

**E1, P2 — Installed release differs from reviewed source.** The active 0.8.7 XPI is SHA-256 `77166feb45d73ba972d8c35a884bac03c70b3871119d87a682df2779b4184aa1`. Its frozen helper lacks the current worker's serialized packet lock, 15-second request keep-alive, and optional NumPy-import fallback. Version labels alone concealed this functional difference. The initial UI reports an inactivity timeout; the retained worker stack log contains no request-heartbeat thread. These observations support the missing keep-alive as the relevant failure route, without proving every cause of the earlier stop. `frontend-package087-mismatch.json` records the exact code-object comparison. Repair: rebuild the existing worker and package as 0.8.8; do not replace a subsystem or add a dependency.

**E2, coverage correction — Ignored first-party audit utilities were absent from the prior inventory.** `tests/make_audit_samples.py` is explicitly ignored by Git. Its 45 lines have now been reviewed and classified as a historical standalone fixture utility. It was not executed against the user's library. The evening inventory also found five historical report scripts under `output/reconciliation/2026-10-09` (1,364 lines), which have been fully reviewed. The final ledger includes those paths explicitly. Earlier completeness claims are qualified by this correction.

The earlier component reports remain the detailed evidence for repaired conflict recovery, Windows filename validation, incomplete-PPTX review, citation metadata selection, runtime integrity checks, PDF eligibility/staged counters, safe traceback sampling, and PyMuPDF stdout routing. See `../2026-10-25/backend-review.md`, `frontend-review.md`, and `shared-review.md`. Original defect reproductions are historical evidence and are not counted as current passing regression tests.

## Coverage and verification method

The current inventory, revision/status/diff snapshots, and file/line ledger are saved in this directory. Coverage is **271 product/historical files /69,233 lines**, plus **14 executable audit-evidence files /1,186 lines**:285 authored files /70,419 lines total, with no uncovered file/range or current hash drift. Unchanged files carry the earlier full line-review evidence only when their current SHA-256 matches. Changed worker/test lines and manifest/guide changes receive fresh review. This records every current first-party code file/range; it does not claim 100% executed branches or manual review of third-party binaries.

Generated audit fixtures/reports, vendored PDF.js, models, native libraries, fonts, environments and build outputs are classified separately. Version/license/provenance checks are retained in the earlier `dependency-provenance.md` and JSON; the new build reuses that existing pinned environment. No new capability or replacement subsystem is implemented, so AGENTS.md's open-source survey requirement does not require a new survey for these routine packaging repairs. Relevant upstream API evidence is recorded in the component reports.

## Initial production state and rollback

`initial-installation.json` verifies installed 0.8.7 active/enabled and its exact XPI hash. `initial-worker-stack.log` preserves the stopped helper's diagnostics before restart; its last modification was 19:24 UTC. A read-only SQLite snapshot found 456 mapped identities, 454 uploaded PDFs, two deliberately suspended staged PDFs, 309 received revisions, and 309 published/indexed receipts. It found no duplicate source/view identities or changed prior baseline digests. `pre-sync-state.json` records the details and limits.

Three approved unlinked PDFs remain intentionally blocked: each matches an existing tablet PDF exactly, and its original filing-home membership changed. The existing duplicate guard requires reference/folder reconciliation; this audit does not choose the reference or create another copy. The three original files remain intact and match their approved digests. Earlier read-only proof is in `../2026-10-25/unlinked-pdf-diagnosis.json`; private titles/IDs stay under `.test-tmp`.

Zotero was closed normally before a fresh backup. The fresh snapshot passed:16 files and 8 SQLite integrity checks. Its rollback location is `.test-tmp/full-audit-20261025/pre-088-evening-backup-complete/`, including `previous-plugin.xpi` (0.8.7), config/encrypted grants, Zotero database and plugin journals. The backup process recovered only disposable copies of stopped databases. Existing earlier rollback snapshots remain in `.test-tmp/full-audit-20261025/pre-085-backup-complete/`; sources and model/cache data are deliberately retained in place rather than duplicated. Backup exclusions are not treated as missing production sources.

## Runtime acceptance

| Check | Current status |
| --- | --- |
| Prior complete regression | 1,459 tests / 119 modules passed; later transport/counter tests ran separately. All28affected repair/transport tests passed after the committed delta. |
| Native/UI feature fixtures | Earlier 53 native/package checks and 30 UI checks passed. Final 0.8.8 targeted native malformed-PDF/transport check passed with14baseline checks, successful reindex, clean status, actual stderr diagnostic, unchanged source/stored bytes, and exit0. |
| Package/source equality | Installed 0.8.7 fails equality. Final0.8.8 comparison passes for31frontend/assets,36Python modules, entrypoint, notice and runtime manifest. |
| Correct installed helper | 0.8.8 active/enabled; live endpoint version and extracted helper SHA match the tested build. `installed-plugin.json`, `installed-helper.json`. |
| Actual configured sync | Started22:51:08UTC on installed0.8.8. Normal saved connection/mapped folders only; no new approvals or ambiguous decisions. |
| Repeat sync/idempotence | Pending first successful completion and before/after state comparison. |
| Real cloud preservation | Earlier read-only checks found all 454 uploaded managed identities and PDF digests present; all 43 new uploads matched. Three fresh blob downloads matched original bytes. This is historical proof, not a fresh physical-device test. |

## Remaining boundaries

The separate Zotero account warning reports full file-storage quota. No storage purchase, account change, mass approval, document deletion, or new pairing is authorized or performed. Physical tablet pen-stroke/firmware behavior, another computer's Zotero account round trip, every upstream binary byte, and every possible concurrency/format combination cannot be certified by local code review and fixtures. The final report will distinguish completed, failed, blocked and unverified checks.
