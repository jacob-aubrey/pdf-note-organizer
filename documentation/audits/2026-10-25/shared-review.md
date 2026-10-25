# Shared integrations, extraction, rendering, search and reader audit

Audit base: HEAD `d84f9516f4ed8b0623e37c3ecdf254cd386687c0`, including the pre-existing local changes captured by `inventory.json`, `initial-status.txt` and `initial-diff.patch`. The initial shared ledger contained 92 files / 23,312 lines: 39 first-party source files / 11,742 lines; 52 tests / 11,540 lines; sorting provenance / 30 lines. All initial hashes matched the coordinating inventory. The ledger now includes both initial and post-repair hashes/line counts; current ranges cover all lines including the repairs below.

## Coverage and method

Every line of all 92 files in `shared-ledger.json` was read with numbered source output. Long files were read in bounded chunks; truncated portions were read again. Full `[1, last_line]` ranges and SHA-256 hashes are recorded individually. This ledger makes no claim about other reviewers' files.

Source scope: all five `remarkable_*.py` modules; `cloud_notes`, `combined_pdf`, `extraction`, both OCR adapters, PDF margins, source storage, exports and citations; all seven sorting modules; all three first-party reader assets; accessible/PDF readers, PDF worker, reader host/navigation/results/server/source/title; match preview/page numbering; research search/tools and search/index. All assigned reader, PDF, cloud, sorting and search tests and four native reader harnesses were read, plus `test_source_storage.py`.

Generated/native/vendor dependencies are not presented as manually reviewed first-party code. Relevant components include PyMuPDF, rmscene, python-docx, pypdf, WebView2/pywebview, Tesseract and Windows APIs. See `dependency-provenance.json` for centrally recorded versions/provenance. Local Python was 3.13.1; the initial shared probes used PyMuPDF 1.28.2, pypdf 6.19.0 and python-docx 1.2.0. `AGENTS.md` and `sorting/PROVENANCE.md` were read. Changes below are focused corrections to existing behavior; no new capability or subsystem replacement was implemented.

## Findings and disposition

### SH-1 — P2, repaired: standalone Inbox Smart metadata could verify a cited paper as the current paper

**Scope: auxiliary standalone Inbox Smart metadata, not current Zotero plugin DOI verification.** Original `note_organizer/sorting/core_logic.py:286-314` ranked reference-list DOIs lower but still tried them. The verifier at original `:344-368` accepted title similarity of at least 0.72 without requiring that the DOI identify the document. Original `:463-478` then adopted the citation and marked it verified with no review.

The isolated fixture gives the document a title ending **“in rabbits”**, author Jane Rabbit/year 2026, and a reference ending **“in rats”** with DOI `10.1234/rats.2025`. The DOI response is Alice Rat/year 2025. Title similarity is **0.9743589743589743**. Before repair the returned proposal changed to the rats paper, selected Alice Rat and said `Verified by DOI metadata`, `needs_review=false`. The Inbox still required user approval before moving the file, but the verification label overstated the evidence.

**Reachability:** `note_organizer/inbox.py:429,459-465` calls `get_document_details` for Smart naming with online lookup enabled. Current plugin `_proposal` calls Basic extraction (`note_organizer/zotero_worker.py:475-477`). Plugin bulk inspection (`note_organizer/zotero_bulk.py:46-58`) imports local extraction and DOI candidate discovery, not this resolver/verifier. Frontend `library.js` has a separate identity check reviewed by the frontend reviewer. This reproduction does not establish a defect in that plugin check.

**Repair:** `core_logic.py:356-359` rejects a DOI appearing only after a standalone References/Bibliography heading unless it also appears before that heading or in embedded properties. Local metadata is retained rather than declaring a reference verified. Regression tests cover the scientifically similar title and preserve legitimate repeated/front-matter and embedded DOI behavior. Bibliographies without a recognized heading and other weak title matches remain limits of the local heuristic; this change does not claim perfect document identity.

**Evidence:** `shared-repro-results.json` records the original false acceptance; `shared-postrepair-results.json` retains the rabbits title/Jane Rabbit and uses local evidence. Extraction/provider responses are deliberately mocked for this probe; it proves the local decision boundary, not live Crossref/DataCite accuracy.

### SH-2 — P3, repaired: partial PPTX extraction could retain a clean review status

Original `note_organizer/sorting/presentation_extraction.py:235-255` skipped missing/unsafe/external slide relationships with warnings; `:129-134` skipped unreadable slide XML. But original `:152` only marked review for empty text and safety limits. One readable slide with complete metadata could therefore produce a clean proposal while another declared slide was missing.

The real ZIP/XML probe generates two slides and removes `ppt/slides/slide2.xml`. Before repair it returned two declared slides, a missing-slide warning, `requires_manual_review=false`, `proposal_needs_review=false` and no review reasons. The original document is retained; this finding concerns the completeness/review signal, not source-content loss.

**Repair:** `presentation_extraction.py` now tracks omitted/unreadable slides and requires manual review. The focused test covers both a missing slide and malformed slide XML with otherwise complete citation fields. The common adapter carries the completeness flag into review reasons. A synthetic call to the actual plugin `Worker._proposal`, including authoritative title/author/year, confirms that the incomplete-format review reason survives and `needs_review=true` (`shared-postrepair-results.json`). No real Zotero import of a malformed presentation was performed.

Plugin `zotero_bulk.py:46-58` still drops detailed extraction warnings from its short inspection result; its readability gate at `:391-394` reads proposal review reasons. The repaired common completeness reason contains “could not read” and now reaches that gate. Native Office/Zotero handling of damaged presentations remains unverified.

### SH-3 — test failure corrected: renderer audit had an obsolete tombstone expectation

The initial full suite's `batch-8.log` failed because `tests/test_render_audit.py:146` expected the generic “annotation items” error for a zero-length tombstone. The current renderer already supports valid CRDT deletion runs and correctly rejected that fixture with “An invalid tablet deletion record requires review.” This was an outdated test expectation, not an annotation-rendering failure.

The test now separately asserts unsupported text items and the specific malformed deletion-record error. No renderer safety check or product rendering code was changed. All five existing `test_tablet_deletion_records.py` regressions still pass, including erased runs/groups and invalid/oversized records; `test_render_audit.py` also passes.

## Feature traces and verification boundaries

| Area | Reviewed behavior and evidence | Runtime boundary |
| --- | --- | --- |
| Cloud authorization/HTTP | DPAPI token storage, redirect restrictions, bounded retry/backoff, cancellation, token renewal, blob/index checksums in `remarkable_cloud.py`; cloud fixture tests | No credentials read or real cloud requests by this reviewer. Mocks do not establish current server behavior. |
| Cloud creation/update/outbox | Scoped parents, deterministic identities, expected item hash/root conflicts, persisted intent and uncertain-commit reconciliation before retry; outbox/cloud tests | Actual account concurrency and server commits require live verification owned by root. Cancellation cannot undo a prior remote commit. |
| Local publication/Windows paths | Staged writes, absent-target publication, mandatory Windows handle/digest guards, recovery copies; guarded race fixtures | Real OneDrive/antivirus contention, disk exhaustion and permissions vary. No user documents were replaced or deleted by this reviewer. |
| Sync and retained sources | Scope routing, PC baseline stability, conflict fingerprints, current/historical raw manifests, baseline/layer hash/path checks in sync/sources/cloud notes | Source/tamper/history/cancellation tests reviewed. Real firmware/archive recovery remains a live check. |
| Annotation/PDF geometry | Page maps, glyph/ink/typed text, opacity/margins, unsupported scene/field/geometry rejection; annotation and pixel fixtures | Synthetic scenes do not establish every firmware/brush/page-map/handwriting case. |
| Combined PDF/export/cleanup | Revision/page-mapping checks, content-addressed reader copies, destination digest guards; cleanup proves migration identity, source reconstruction and notebook links | Source and disposable race/history tests reviewed. No real-library cleanup executed. |
| Extraction/OCR | Quote/comment extraction, preview geometry, deferred tablet marks, versioned OCR cache and subprocess cancellation/timeouts | OCR subprocesses are mocked in many tests; installed language packs and real handwriting quality remain unverified. |
| Citations/notebooks | Shared logical identity, citation export deduplication and escaping; source hyperlinks and guarded DOCX writes | Fixtures reviewed. Native Word layout/hyperlink behavior needs rendering/application verification. |
| Search/index | Boolean parser, Unicode/casefold/hyphenated flow, enabled fields, merged note/PDF scope, cancellation, stale-file warnings and digest/version cache keys | Static/test coverage reviewed; centralized suite supplies pass/fail results. |
| Reader HTTP/security | Loopback binding, tokenized paths, Host/Origin/source version validation, asset confinement and byte ranges | Full reader server source/tests reviewed; no user PDFs served by this reviewer. |
| PDF worker/native reader | Spawned parsing process, prioritized/serialized jobs, chunked extraction, latest-generation authority and error recovery | Cooperative cancellation cannot interrupt a native parser that never returns; host shutdown/UI require runtime checks. |
| Reader UI | Main/PDF Find authority, mapped occurrences, retained transitions, zoom/pan/links, latest result, disabled edit/forms/scripts, text-only title insertion | Four opt-in harnesses use generated PDFs and verified inactive desktops; successful execution is live WebView2 evidence. Reading the tests alone is not a pass. Root owns native execution/results. |
| Sorting/provider boundaries | Format/path bounds, exact DOI provider requests, local/AI fallback, DPAPI helper and filename validation | SH-1/2 demonstrate gaps in prior fixture coverage. No real Gemini/metadata service requests by this reviewer. |

## Commands and results

- Numbered PowerShell `Get-Content -LiteralPath <file>` reads with bounded ranges, plus `rg` caller/guard searches; complete final coverage is recorded in the ledger.
- `.\.venv\Scripts\python.exe documentation/audits/2026-10-25/shared_repro.py`: initial **exit 0**, two defects reproduced in `shared-repro-results.json`; post-repair **exit 0**, corrected outputs in `shared-postrepair-results.json`. Fixtures stay in temporary audit-owned directories and are removed.
- `.\.venv\Scripts\python.exe -m unittest -v tests.test_render_audit tests.test_tablet_deletion_records tests.test_sorting_presentation_extraction tests.test_sorting_smart_metadata_integration`: **41 tests passed**, `shared-repair-tests.log`. Set `TEMP` and `TMP` to the existing workspace-owned `.test-tmp/shared-audit-repair` before running. A first attempt using the sandbox-default temp location failed with filesystem PermissionError; rerunning with the owned directory resolved that environment issue.
- SHA-256 / `ReadAllLines` ledger generation and comparison with initial inventory: all initial shared hashes matched; five explicitly repaired files now differ. Both hashes are retained in the ledger.
- Broad suites/build/static/native reader execution are centralized by root to avoid duplicate runs; consult the final report/logs for those results. No independent all-suite pass is asserted here.

Primary upstream material consulted: [PyMuPDF Document API](https://pymupdf.readthedocs.io/en/latest/document.html) and [rmscene upstream](https://github.com/ricklupton/rmscene). rmscene describes reMarkable v6 parsing; it does not certify every firmware/device. Documentation may describe newer versions than the installed runtime, so version inventory and actual runtime tests remain essential.

Static review and fixture passes cannot establish that everything works. This reviewer performed no real library/device/cloud mutations; root owns the user-authorized installation and real sync. Unavailable live application/device cases must remain explicitly unverified in the final report.
