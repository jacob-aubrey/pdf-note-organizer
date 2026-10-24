# Bulk onboarding and exception-only review

On October 22 the user approved processing routine papers together and flagging
only obvious or suspected problems. Missing citation fields are not a reading
or tablet-sync gate. The user normally checks references when preparing a final
bibliography. Publisher/DOI metadata is preferred over PubMed when available.
This supersedes the October 20 requirement for individual approval of every new
document. No production library migration or tablet reorganization is performed
by development or packaging.

## Existing work checked first

- Zotero's documented [PDF metadata retrieval](https://www.zotero.org/support/retrieve_pdf_metadata)
  already creates parent references and retrieves citations for batches. It may
  fail or return incomplete metadata; no high-confidence universal recognition
  claim is made. Reuse the installed native recognizer and DOI translators.
- The actual Zotero **10.0.6 Windows x64** `app/omni.ja` was inspected. Its native
  `Attachments.importFromFile`, `RecognizeDocument.recognizeItems`,
  `Translate.Search` with `libraryID:false, saveAttachments:false`, and normal
  personal-library APIs implement the storage/metadata operations. This avoids
  copying a second PDF from a publisher or creating a separate metadata service.
  [Upstream implementation](https://github.com/zotero/zotero/blob/main/chrome/content/zotero/xpcom/recognizeDocument.js).
- Zotero is actively maintained upstream and installed separately under
  [AGPL-3.0](https://github.com/zotero/zotero/blob/main/COPYING). These are internal,
  version-sensitive APIs: the package remains restricted to **10.0.x**, and live
  acceptance checks use 10.0.6. Windows compatibility is checked in the real SDK;
  no claim is made about Zotero 11 or other platforms.
- The existing bundled **pypdf 6.19.0** (BSD-3-Clause, pure Python, Windows
  compatible) and this project's extraction/DOI-ranking helpers provide local
  structural checks and evidence. The maintained [pypdf project](https://github.com/py-pdf/pypdf)
  does not identify a paper or perform library deduplication on its own.
- Standard Python `hashlib`, `pathlib`, `os.walk` and the existing atomic-write,
  SQLite review journal and bridge provide digest grouping, selected-root
  traversal, resumability and tablet annotations. A third-party duplicate-file
  app would not know Zotero parents, citation curation or tablet identity and
  would add another recurring user interface. A small planner is still needed.

No new runtime dependency, user CLI, Python setup, AI account or external tag
manager is introduced. Existing licenses/notices remain bundled.

## Resulting behavior

- One recursive read-only folder scan, one summary, one action for routine
  imports/reuse. Original folders and files remain in place. Windows categories
  are not automatically reproduced on the tablet.
- Exact bytes group duplicate source copies and locate existing Zotero PDFs.
  DOI/title similarity only flags a possible version/reference conflict; it
  never authorizes overlaying tablet ink onto another file.
- Publisher/DOI translators are queried first for locally extracted DOI
  candidates. Candidate titles must be supported by the PDF text. The ordinary
  Zotero PDF recognizer is the fallback. Its normal lookup sends initial text
  to Zotero; the control can be disabled for local-only intake.
- Empty citation fields keep the PDF usable. Scans are eligible even without
  machine-readable text. Broken/encrypted files, ambiguous attachments,
  possible versions and unassigned SI are exceptions.
- Routine filing decisions are applied together to a chosen tablet destination.
  Exact unambiguous tablet matches retain their recorded mapped homes. Reference
  metadata, collection memberships and user notes remain protected by the same
  bridge/native adapters; the original source is rehashed before each action.
- The toolbar badge counts exceptions instead of hundreds of routine files.
- A long-running native test exposed an interrupted/stale localhost connection.
  SDK requests now close their connections, action polling uses fresh guarded
  connections, and only idempotent import/read operations retry (three attempts).
  Completed native job results remain replayable after a lost response, bounded
  to 1,000 cached jobs. An ongoing connection failure pauses the saved batch;
  it does not mark every remaining PDF defective or continue hundreds of waits.
  Resuming rechecks native content and reuses any already-committed copy.
  Routine filename previews are optional. Metadata corrections remain available
  in Zotero before citation use.
- One tablet Literature folder is compatible with overlapping topic tags.
  Existing folders are not flattened. Tablet tags currently flow into Zotero;
  full bidirectional tag editing/removal is a separate, unimplemented capability.

## Validation

Validation results are recorded after the automated and native acceptance runs.
All native fixtures use disposable profiles and synthetic documents. No real
library, source PDF or tablet account is modified by those checks.

Repeated intake of content already stored in the selected collection performs no
native write or metadata lookup. It revalidates the source against the indexed
content and records reuse, including the private baseline of an annotated view.
Read-only reuse checkpoints can safely be batched because replay has no mutation.
