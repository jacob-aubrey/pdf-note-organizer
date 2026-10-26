# Evening inventory and shared-source review

The evening target is HEAD `7bdb3a63bf198692883286749693fca9cabcb78d` on `main`. The initial tracked working tree and index were clean; newly created evening audit outputs are separately identified in `initial-status.txt`. `initial-diff.patch` and `initial-index-diff.patch` are empty. The later `current-status.txt` / `current-diff.patch` record the root reviewer's authorized, uncommitted 0.8.8 manifest/guide edits and the audit-only forensic-probe parser correction. `revision.json` and `revision-current.json` preserve both snapshots.

Every subject file was SHA-256 hashed. Existing ranges were reused only for identical bytes, with the prior ledger path, ledger SHA-256, file hash, range and reviewer evidence retained in each entry. This is reuse of the earlier full line review, not a claim that unchanged files were reread tonight. Binary assets have null line counts in the new inventory; earlier binary line-like byte counts are retained only as prior metadata and do not imply source lines or a content change.

No shared runtime source changed. All 39 previously reviewed shared source files remain byte-identical to their earlier reviewed versions. Exactly two existing code files changed against the prior unified ledger: `note_organizer/zotero_worker.py` (+19 lines) and `tests/test_zotero_transport.py` (+26 lines). Their fresh backend review and reconstructed prior-source evidence are in the evening backend ledger. The 0.8.8 guide and manifest changes have fresh frontend review. No product change was made by this reviewer.

## Previously omitted ignored authored utilities

The filesystem metadata pass found six first-party Python utilities hidden by ignore rules. All six were fully read tonight, independently inventoried/hashed and parsed with `ast.parse`, without importing or executing them. They total **1,409 lines** and are explicitly marked historical ignored audit utilities in `historical-utilities-ledger.json`.

| Utility | Lines | Reviewed behavior |
| --- | ---: | --- |
| `tests/make_audit_samples.py` | 45 | Generates synthetic audit JSON and optionally reads a local library/PDF for comparison; writes only its `tmp/audit` reports. |
| `output/reconciliation/2026-10-09/cloud_helpers.py` | 362 | Exact configured source/root guards, read-only SQLite settings, protected pairing, cloud GET/session renewal allowlist, validated metadata/cache reads, complete/stable-root checks and scoped JSON/CSV exports. |
| `output/reconciliation/2026-10-09/pc/inventory_pc.py` | 277 | Metadata-only filesystem inventory, original PDF hashing/annotation/text statistics, duplicate candidates and pre/post snapshots; writes its own report directory. |
| `output/reconciliation/2026-10-09/pc/verify_and_report.py` | 84 | Independent pypdf sample comparison and report assembly from saved inventory data; writes only report outputs. |
| `output/reconciliation/2026-10-09/build_assessment.py` | 273 | Combines saved inventories into evidence-ranked match candidates and an advisory assessment. No file/cloud move or deletion API. |
| `output/reconciliation/2026-10-09/folder-critique/build_pc_structure_critique.py` | 368 | Produces proposal-only folder mappings, coverage/uniqueness assertions, an advisory narrative and proposed path-length analysis; no physical relocation. |

The two assessment builders and `verify_and_report.py` embed dated narrative statements and numeric counts (`build_assessment.py:173`, `:189`, `:201-203`; `verify_and_report.py:53-76`; `build_pc_structure_critique.py:161-336`). They are historical one-off report generators, not general current-state verification tools. Rerunning them on different input could mix newly computed tables with old narrative. They were not run tonight and provide no evidence about today's cloud/library state. This limitation has no demonstrated reachability from the installed plugin.

The report-script source includes private research filenames and workflow notes; those details were not copied into this audit's public findings. No live database, credentials, real PDFs or cloud APIs were opened by this reviewer during the evening pass.

## Scope and exclusions

The subject inventory contains **819 Git-visible paths plus six relevant ignored authored files**. The product/historical source subtotal is **271 files / 69,233 lines**: the 265 Git-visible code files total 67,824 lines; the six ignored utilities add 1,409. Of these, 263 unchanged code files inherit valid prior review, two changed code files have fresh backend evidence, and six newly inventoried utilities were fully read tonight. The empty `tests/__init__.py` has zero lines and no range to omit.

`ignored-inventory-summary.json` records the completed filesystem name/type/size traversal separately: environments, generated builds/packages, private app data/exports, bytecode, historical scratch outputs and test/cache data were classified without reading their contents. Its aggregate counts can change during the root reviewer's concurrent build. The five report scripts discovered by that traversal were subsequently promoted into the authored inventory; they are not silently excluded as output. Git internals and this audit's newly generated outputs are excluded from the subject snapshot and tracked separately as audit evidence. Generated JSON/logs/images and dependency/source copies inside environments or fixtures do not inherit a manual first-party line-review claim.

Executable scripts under `documentation/audits` were separately reviewed by the backend reviewer and merged from `audit-evidence-code-ledger.json`: **14 files / 1,186 lines**, including two newly created evening scripts. This gives **285 authored code files / 70,419 lines** across both explicitly separated scopes. The combined inventory has 827 entries: the 825-file subject snapshot plus the two new executable evidence scripts. All current authored hashes and complete ranges verify, with no remaining gap; generated JSON/logs/images are evidence data rather than executable code. See `audit-evidence-code-review.md` for the corrected mutually exclusive forensic-probe flags and execution/privacy limits. Historical reproduction scripts were not rerun merely to refresh their evidence.

The ledger is a source-review statement. It does not establish fresh runtime or live-sync success. The root reviewer owns the new package, installation and synchronization verification.
