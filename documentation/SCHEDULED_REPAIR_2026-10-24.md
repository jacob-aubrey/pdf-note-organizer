# Scheduled repair session — October 24, 2026

The one-time task ran in the existing PDF Note Organizer project and chat. The
schedule was deleted at invocation so it cannot repeat. Changes remain local;
nothing was pushed or merged. Production Zotero profiles, accounts, and tablet
documents were not used for these repairs or their regression tests.

## Existing work

Four files already had edits when the session began: `printed_ocr.py`,
`zotero_pilot.py`, `zotero_review.py`, and `zotero-support/library.js`. Those
changes were retained and extended. Their starting patch is saved locally at
`.test-tmp/scheduled-repair-20261024/preexisting.patch`.

## Repairs

- Local PDF replacement now preserves the account's last-synced hash/time in a
  durable upload receipt, verifies replacement bytes, restores the account
  precondition, and explicitly marks the attachment for account upload. A lost
  response or interrupted completion resumes the receipt without uploading the
  PDF twice. Preparation is read-only, closing the interruption window before
  the receipt is saved. Approved intake uploads use the same durable mechanism
  for ordinary stored attachments, including Word and PowerPoint sources.
- DOI metadata must match the document's independently extracted title.
  Bibliography text is no longer identity evidence. The side-effecting native
  recognizer is not used as an unvalidated fallback; uncertain imports retain
  local document metadata and a review explanation. A failed file copy cannot
  leave a newly created empty citation. Native imports serialize by content
  across destination choices.
- Original staging precedes durable bridge registration. Old incomplete
  registrations recover from verified source bytes. Linked-file originals are
  preserved and receive a supported managed view. One attachment's move retains
  collection membership still required by its linked siblings.
- Missing local files are isolated per paper. Missing tablet-origin papers are
  marked unavailable and excluded from connected counts without treating absence
  as deletion. Deleted folder subtrees no longer break unrelated selected roots.
- Unchanged tablet PDFs and strokes reuse integrity-checked retained sources and
  the existing baseline cache. Rendering receives the existing cancellation
  callback and checks cancellation before producing its final output.
- Interrupted matched approvals recognize completed counterpart steps. External
  Zotero restores clear obsolete deletion decisions. Failed tablet restore
  validation no longer traps an action in its applying state. Changed or removed
  intake reviews are retired; pending intake reviews can be dismissed.
- Bulk import validates its visible folder, destination, and lookup settings;
  retries keyword application after an earlier import committed; counts eligible
  work; distinguishes cancellation and incomplete work; and supports individual
  exception recheck/retry/dismiss controls.
- Explicit reconnect archives the previous binding instead of reusing its links
  against another Zotero instance. Local settings remain usable offline. Intake
  excludes the actual Zotero data/storage directory even when empty. Personal
  names use structured creator fields and freeform dates retain their year.
- Failed printed OCR remains retryable indexing work. Otherwise empty screenshot
  and outlined-text pages receive OCR. Partial-index warnings reach the review
  interface without exposing credentials or diagnostic file paths.
- Reading PDFs restore bookmarks and links after page insertion, reordering,
  deletion, and geometry changes. Historical sources belonging to explicitly
  deleted tablet pages remain retained without blocking live page rendering.
- Helper shutdown coordinates with startup, malformed output stops the old
  process, idle requests have bounded recovery, and the existing extractor can
  repair damaged bundled helpers. Filing saves serialize rollback with later
  mutations and validate saved queue entries.
- Tag, review, and rename/move drafts survive redraws with stale revision guards;
  keyboard focus is restored where possible. Reader tagging opens the workspace
  before waiting behind background work. Explicit article classification can
  override an SI heuristic. Collection menus reconcile additions and deletions.
  Linked papers and import exceptions have filters; the elapsed clock sits
  outside the screen-reader live region.
- Windows CI installs the existing private plugin requirements, checks dependency
  consistency, and discovers all plugin JavaScript syntax/regression suites.

## Reuse and version checks

These are adaptations to existing components, rather than replacement sync,
rendering, recognition, or process-management systems. No new runtime dependency
was added.

| Existing component | Verified capability and decision |
| --- | --- |
| Zotero 10.0.6 on Windows, build 20261007153950 | Inspected installed `server_localAPI.js`, `storage/zfs.js`, and `data/item.js`. Local uploads overwrite synced metadata; account uploads use that hash for `If-Match`; stored attachments support `attachmentSyncState='to_upload'`. Reuse native operations with durable receipts. Synthetic tests establish adapter behavior; a real account round trip is not established. |
| Pyzotero 1.16.0, BlueOak-1.0.0 | Installed package metadata supports Python 3.13 and OS-independent use. Retain its existing local upload client and pass the correct authorization hash. Its existing `httpx2` dependency is present in the packaged runtime. |
| PyMuPDF 1.28.2, AGPL-3.0 or Artifex commercial | Existing Windows Python 3.13 installation and package license checked. Its maintained document/link APIs support the required repair; copying single pages intentionally omits links outside that range, so a small destination-remapping adapter is necessary. Existing Tesseract binding performs OCR without adding a service. |
| rmscene 0.8.0, MIT | Existing version parses tablet v6 scenes. Retain the parser and source archives; ignore historical page layers only when their page has an explicit deletion record. No new firmware-support claim. |
| Mozilla Subprocess in installed Zotero | Inspected `subprocess_common.sys.mjs`: `kill()` returns the exit promise and Windows force-terminates the process. Reuse that lifecycle API and the existing bundled-runtime extractor. |
| Zotero metadata-only DOI translators | Can return metadata without saving attachments or references, allowing title verification first. The native document recognizer saves before equivalent verification is possible; it is therefore unsuitable as this automatic fallback. |

References: [Zotero local API](https://www.zotero.org/support/dev/web_api/v3/local_api),
[PyMuPDF document APIs](https://pymupdf.readthedocs.io/en/latest/document.html).
Actual installed implementations and regression results were checked in addition
to documentation. No upstream support for a behavior was inferred merely from a
repository's feature claim.

## Validation and limits

| Validation | Final result |
| --- | --- |
| All `test_zotero*.py` modules | 203 tests passed in 172.515 seconds. Log: `.test-tmp/scheduled-repair-20261024/plugin-validated.log`. |
| Shared PDF, OCR, sources, storage, and deletion modules | 168 tests passed in 118.395 seconds. Log: `.test-tmp/scheduled-repair-20261024/shared-validated.log`. |
| Final publication/navigation/OCR/deferred-margin recheck | 20 tests passed, including the added cancellation-during-navigation case. This overlaps the broader suites. |
| JavaScript controller/native endpoint suites | All five `tools/test_zotero_*.cjs` suites passed. |
| Real Zotero 10.0.6 integration | 32 checks passed against a disposable profile and in-memory synthetic cloud. |
| Rendered native UI | 30 checks passed across actual rendered layouts, themes, and native controls; selected narrow/dark and active-review screenshots also inspected. |
| Additional real native checks | 3 checks passed: null prior sync hash on an ordinary attachment, correct byte replacement/account receipt/TO_UPLOAD, and citation-lookup-disabled title preservation. |
| Static/dependency checks | Python compilation, every plugin JavaScript syntax check, `pip check`, and `git diff --check` passed. |
| Packaging smoke | A test-only frontend XPI contains all 31 current source assets byte-for-byte and no credential/library files. It is not a full runtime release. |

Native JSON results and 30 screenshots are retained under
`.test-tmp/scheduled-native-20261024-r2/`. The disposable Zotero process closed
cleanly through its fixture's close marker. The production profile was not
opened by the test harness.

Tests used the project's existing Python 3.13 environment plus dependencies
extracted from the existing packaged helper, rather than installing new global
packages. Missing timezone payload in that extracted test environment was
restored from the existing package before the successful native rerun. Initial
sandbox denial of the private desktop/socket was resolved by automatic approval
for the same synthetic tests; no approval was rejected. Intermediate failures
found during integration were corrected and the relevant checks rerun, including
the actual native hash setter's requirement for `null` rather than an empty hash.

Commands for the broad suites (with the existing plugin dependencies available):

```powershell
python -m unittest discover -s tests -p 'test_zotero*.py' -q
python -m unittest tests.test_printed_ocr tests.test_remarkable tests.test_combined_pdf tests.test_pdf_margins tests.test_deferred_scene_margins tests.test_remarkable_sources tests.test_tablet_deletion_records tests.test_source_storage tests.test_handwriting_ocr -q
```

No test failures remain in the completed checks. GitHub-hosted CI itself was not
run because the changes were not pushed. Bulk cases with genuinely ambiguous
citations or editions still require a human decision in Zotero; retry/dismiss
does not guess a citation or merge references.

Live tablet firmware behavior, a real multi-computer Zotero account round trip,
and concurrent account synchronization remain unverified. Unsupported annotation
formats and the existing rotated/cropped tablet-margin restriction remain
explicit boundaries. The private-preview automatic-update URL remains a
placeholder; no hosting or release distribution was invented. The installed XPI
and its bundled helper are not updated by saving these source repairs.

## Follow-up during authorized library recovery

Version 0.8.1 reuses the existing pypdf 6.19.0 dependency (BSD-3-Clause, already
supported in the Windows runtime) to rebuild a separate rendering source when
MuPDF encounters a dangling object reference. Every page's pixels, geometry,
links, annotations, labels, bookmarks, and embedded files must survive validation;
forms or a changed appearance stop the repair. Raw sources remain unchanged.
The affected 21-page PDF retained all page images, 495 links, and 18 bookmarks.
Synthetic regressions reproduce the missing-reference error and verify retained
tablet ink, cancellation, and rejection of changed content. A MuPDF format error
also remains isolated to its paper. The affected suites passed 111 tests; the
packaged helper passed 10 native checks. No new dependency or service was added.

## Evening repair

0.8.2 reuses the current Zotero 10 collection and file APIs and the existing
scoped bridge for source-folder reconstruction; content matching remains separate
from folder matching. Stable collection keys and case-insensitive sibling reuse
make interrupted folder creation recoverable without another dependency or setup.
The existing PyMuPDF Windows runtime supplies text blocks to keep keyword columns
separate. This small adaptation replaces cross-column text reading, not the PDF
or annotation subsystem. Original PDFs supply keyword evidence; export metadata
is filtered. Existing links receive a versioned keyword check, including explicit
no-keyword, unreadable-text and failure states. No statistical topic suggestion
becomes an automatic tag. Metadata-triggered file renames are followed by a new
native path lookup; saved paths do not identify attachments.

The native local JSON API does not apply attachment parent changes. Reparenting
therefore uses a small guarded native action: the original parent and file MD5
must match, Zotero saves the new parent, and the caller verifies the same
attachment key and bytes afterward. Retries accept an already-completed move.
The packaged extension passed this check in an isolated Zotero 10.0.6 profile.
PDF-bearing references are not merged directly: verified attachments must first
be retained under their intended parent, leaving an empty reference to merge.

The real backfill also exposed a publisher's control-byte keyword bullet. The
reader now separates those keywords and rejects control characters in labels;
tag transfer validates its target before editing either side or its retry
journal. A regression retains an unrepresentable manual tag without a partial
write. Existing manual tags are never shortened to fit the tablet API.

## Live library verification follow-up

The production 0.8.2 sync retained its last Zotero filename while scanning the
tablet catalog. Version 0.8.4 reports real catalog, paper-check and upload stages.
It reuses a catalog only after checking that the cloud root hash is unchanged;
returned snapshots remain independent and writes still check cloud generations.
The existing bounded blob cache tracks its verified size after a scan and scans
again when its byte budget is exceeded, instead of walking thousands of cached
files after every metadata download. Hash verification and the cache limit remain.

The real cold library also exposed timeouts from serial item.loadAllData calls.
The native endpoint now uses Zotero.Items.loadDataTypes(items), the public batch
loader verified in the installed Zotero 10.0.6 DataObjects source. The existing
Zotero component is reused without a dependency or platform/version change.
An endpoint regression catalogs 1,000 synthetic references/attachments with one
batch call and excludes annotation entries; isolated packaged checks exercise
the actual native API. A fresh production startup passed the catalog stage and
continued into verified tablet uploads. Full live-transfer receipts are retained
locally with the pre-run library backup, outside the source release.
