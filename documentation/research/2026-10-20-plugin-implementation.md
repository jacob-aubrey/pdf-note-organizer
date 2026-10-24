# Graphical Zotero integration implementation

The user approved implementation of the Zotero-first interface on October 20.
This supersedes the developer CLI as the intended user experience.

## Accepted contract

- Every new PDF/Word/PowerPoint document enters one review queue, including
  browser captures, local intake and tablet additions. Routine annotation
  revisions do not require naming review again.
- Review shows the proposed filename, reference metadata, research collections
  and one tablet destination. Naming templates are editable per document type.
- Zotero manages local attachments. No parallel user-maintained literature tree.
- Multiple research collections do not duplicate the tablet document. A dedicated
  mapped tablet collection tree identifies its single tablet home.
- Pairing, scope selection, intake, status, sync and recovery are graphical.
  Any processing companion is packaged and managed by the plugin.
- A confirmed tablet trash operation creates a pending decision: restore on
  tablet, trash matching PDF only in Zotero, or trash the whole reference with
  its notes and SI. Closing the dialog leaves the decision pending. Missing
  items/network errors do not prove deletion. Trash is not permanent erasure.
- Renames/moves follow recorded mappings; conflicting concurrent changes require
  review. Removing one research collection membership is not a document deletion.
- Tablet marks and raw sources remain preserved. Expand returned-page bounds to
  avoid clipping ink rather than modifying uploaded originals to add margins.
- OCR stays; hosted AI naming, native tablet notebooks, Word notebook exports,
  custom Boolean parsing, screenshot grouping UI and custom read-only mode are
  excluded/deferred as agreed. Native Zotero SI behavior stays.

## Reuse decision

Use the existing tested Python cloud/source/render/OCR/publisher modules and
Notable naming/extraction helpers. Zotero's own bootstrap, MenuManager,
PreferencePanes, ItemPaneManager, attachment, collection and trash APIs supply UI
and library operations. Use supported interfaces instead of direct database
writes. The earlier `bpiwowar/zotero-remarkable-sync` investigation supplies
tag selection, explicit mappings, scheduling and safe-mode lessons; its released
version excludes Zotero 10 and does not supply the required collection/review
contract. Its source is AGPL-3.0-or-later. No third-party plugin is silently
installed or compatibility-forced.

Primary references checked again before implementation:

- https://www.zotero.org/support/dev/zotero_10_for_developers
- https://www.zotero.org/support/dev/zotero_7_for_developers
- https://github.com/windingwind/zotero-plugin-template
- https://github.com/bpiwowar/zotero-remarkable-sync/tree/v0.2.0

The existing official Zotero 10.0.6 portable package is the Windows runtime test
target. Production Zotero 9 and real libraries are not development fixtures.
Zotero's bundled source provides exact version-specific method signatures.

## Execution record

The graphical extension now opens a native Zotero-hosted workspace, owns its
private stdio worker process and bundles local OCR rather than requiring a
user-operated Python environment. Normal Firefox Subprocess uses
CREATE_NO_WINDOW on Windows; a hidden development launch preference exists only
for disposable source tests and has no end-user runtime-path control.

Native Zotero 10.0.6 tests have passed naming gates, one tablet copy, native
thesis fields, multiple research collections, rename/move both directions,
explicit restore, PDF-only Trash preserving notes/SI, whole-reference native
Trash, changed-note protection, and reviewed PDF/DOCX/PPTX intake with verified
cleanup. The actual workspace was captured through its own test instrumentation
and visually inspected. Windows computer-use identification confused portable
Zotero 10 with the registered Zotero 9 application, so no production UI was
operated to work around that tool problem.

The live metadata writer was tested only against the previously recorded
synthetic PC paper in the validation subtree. Rename, move, Trash and explicit
restore preserved every non-metadata source byte. All other cloud item hashes,
including the user's physical pen-stroke validation paper, remained unchanged.

The first packaged OCR run exposed the Windows piped-stdin/NumPy import hang.
Its stack matched the actual upstream report, rather than an OCR model failure:
https://github.com/numpy/numpy/issues/24290 . The existing workaround is to
preload NumPy on the main thread before starting the stdin reader. This is also
documented in https://github.com/modelcontextprotocol/python-sdk/issues/2832 .
The plugin applies that startup order without copying another transport library
or replacing the recognizer. NumPy is BSD-3-Clause, already an OCR dependency;
its tested 2.5.4 version and OpenCV headless 5.0.0.93 are pinned for the package.

## Final acceptance

- **314 automated tests passed** in 161.451 seconds across the bridge,
  publisher, review/worker, cloud outbox and source retention, OCR, intake and
  existing naming/classification modules.
- **16 packaged acceptance checks passed** against Zotero 10.0.6 in a new
  disposable profile (`.test-tmp/zotero-plugin-release-15/results.json`). These
  include the actual bundled helper recognizing the saved physical-tablet
  handwriting-only keyword, image-only scan retrieval, and native Zotero
  comment retrieval without rewriting the PDFs. The tested XPI was installed
  as a normal profile extension; Python paths were not used by that plugin.
- **6 live cloud checks passed** (`.test-tmp/zotero-plugin-cloud-01/results.json`)
  against the previously recorded synthetic PC validation paper. It was
  restored to its original name and folder. All other item hashes and all
  PDF/annotation source bytes remained unchanged.
- The final package contains only the frontend, manifest and one bundled
  executable, with a verified runtime checksum. No test profiles, credentials,
  library databases or papers are included. A final status-label polish was
  syntax-checked separately; it changes no worker or sync behavior.
- The deliverable is `dist/Notable-for-Zotero-0.2.0.xpi`, with a setup guide,
  component notices and SHA-256/validation metadata alongside it.

Production plugin installation/migration has not been performed. The installed
application was verified as Zotero 10.0.6 on October 20, 2026, correcting the
earlier stale Zotero 9 identification. This package requires Zotero 10.0. The guide
explicitly records unsupported expanded rotated/cropped margins, independent
desktop-note protection, and mapped-folder deletion/out-of-scope review limits.
Unknown or conflicting data is retained for review; this is a validated local
preview, not a claim that every device/PDF edge case works flawlessly.
