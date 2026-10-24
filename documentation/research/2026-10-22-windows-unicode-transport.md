# Windows Unicode transport recovery: 0.4.1

The production plugin completed metadata/folder checks for 140 tablet PDFs but
terminated when writing its status packet. The private transport used
`json.dumps(..., ensure_ascii=False)` through a Windows cp1252 stdout pipe.
A title containing U+2010 caused an unhandled UnicodeEncodeError outside the
request handler. The UI therefore displayed a stopped-helper error, without
rendering the retained pending reviews. No publication had been approved:
the local bridge contained zero document links, and the review store contained
140 pending cloud documents (139 routine and one supporting-information case).
There were 139 cached PDF files because identical PDF content shares one cache
path. These observations came from read-only SQLite connections and snapshots
of the plugin's own state, not direct writes to Zotero's database.

This is a transport bug fix using existing Python JSON and text streams; it
does not replace an integration or require a new component survey. Packets now
use ASCII-safe JSON escaping, preserving Unicode through legacy code pages.
Incoming Gecko requests explicitly decode UTF-8 so tags, filenames and titles
are not silently corrupted in the reverse direction. The same packet writer
handles normal results, interrupted results and progress. New unlinked tablet
documents say Checking, while existing links say Syncing. The UI states how
many pending documents are waiting in Review before filing/transfer.

Validation:

- The exact previous frozen helper failed on the copied 140-document queue
  with U+2010/cp1252 UnicodeEncodeError. The new frozen helper returned all 140
  records in one valid 350,293-byte ASCII JSON packet, with Unicode intact and
  no cloud calls.
- The related 89-test suite passed. Two added regressions exercise a cp1252
  output stream with 140 Unicode records and a subprocess with UTF-8 requests,
  cp1252 defaults, Greek/CJK/emoji text, progress and normal responses.
- Eleven native/package workflow checks passed in disposable Windows Zotero
  10.0.6, including folder changes, restoration, disconnect and OCR/search.
- The native workspace rendered the recovered queue and its File 139 routine
  documents together button, with the explicit 140-document Review message.
- JavaScript syntax and diff whitespace checks passed.

Local evidence: `.test-tmp/zotero-041-unit-results.json`,
`.test-tmp/zotero-041-unicode-results.json`,
`.test-tmp/zotero-041-recovered-ui.json`,
`.test-tmp/zotero-041-native-01/results.json`. The 0.4.1 package was not installed
into the production profile during these tests. No production files or records
were changed and no pending import was approved.

## Proposed Windows intake

A read-only inventory of the user's Bonitatibus Research folder shows why a
whole-root intake would be inappropriate: it mixes papers with grants, drafts,
presentations, data and program files. Start with Literature. That subtree has
537 PDFs with 522 distinct SHA-256 values (15 additional exact copies), plus
42 Word and nine PowerPoint files. Of the 522 distinct PDF contents, 137 exactly
match pending tablet PDF content. This is byte identity, not a title/DOI guess.
It does not establish that every other file is a distinct scholarly article.

Recommended sequence: install the encoding fix, scan Literature using Import
library into the existing Windows imports collection, inspect the routine and
exception summary, import/reuse PC originals, then sync and file the matched
tablet/desktop documents. Starting with PC intake allows native citation
recognition before the existing tablet editions are linked. Exact matches can
retain tablet positions and annotations. Versions with different bytes and
supporting information remain exceptions. Word/PowerPoint files can live in
Zotero, but need PDFs for reading on the tablet. Original Windows files stay in
place; there is no need to reproduce all Windows categories on the tablet.

The existing source backup and offline OneDrive availability help intake. They
do not back up Zotero's separate managed data or the private plugin state.
Keep Zotero's active data directory outside the OneDrive source tree and back
up both Zotero data and its profile's complete notable directory separately.
