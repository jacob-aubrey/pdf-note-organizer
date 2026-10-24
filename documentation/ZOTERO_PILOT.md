# Zotero companion pilot

**Historical first-stage publisher notes.** The implementation now also has a scoped bidirectional bridge, printed OCR, encrypted reconnection and a small Zotero support extension. Use [the current companion guide](ZOTERO_COMPANION.md) for present behavior and validation. Counts and implementation boundaries below describe the initial publisher stage.

This is the first working implementation of the Zotero-centered direction discussed on October 18, 2026. It is an **optional developer pilot**, not an installed Zotero plugin, automatic background service, production migration, or completed tablet synchronizer. The working Notable application is unchanged.

Zotero supplies the visible library and bibliography. A small Python companion uses its supported **local API**. A thin Zotero plugin can be added later if setup/status controls or native annotation integration need it; the existing Python tablet/PDF processing does not need to be rewritten in JavaScript.

## Implemented

- Prepare one explicitly selected logical paper from a Notable library, using its existing guarded combined-PDF renderer and saved tablet sources. The Notable SQLite connection is read-only; rendering may populate the existing rebuildable reading cache. Originals and saved tablet sources are not rewritten.
- Carry over selected saved highlight quotations, typed comments and handwriting/OCR transcripts, including their source/page provenance, into the prepared manifest. Unrelated papers' saved annotation text is excluded.
- Preview publication without modifying Zotero. Preview creates helper-owned state/snapshots in the supplied state directory.
- On explicit apply, request Zotero's normal local write permission and create a separate **Notable Pilot** collection, references and marked PDF attachments.
- Accept native Zotero bibliographic metadata, including Thesis fields. Existing Zotero reference titles, tags and other reviewed metadata are left authoritative after creation.
- Refresh the **same attachment key** for later prepared PDF revisions. This updates a durable managed PDF in Zotero storage rather than only a Notable reading cache.
- Reuse stable source identities, retain previous prepared PDF versions, and resume after uncertain upload confirmation or failed text indexing.
- Reject a different Zotero instance/source namespace, independent edits to a managed PDF, missing published items, changed ownership, and concurrent runs against the same helper state. Deleted pilot records/collections are not silently recreated.
- Support a main PDF and SI files as sibling attachments of one reference through explicit `reference_id`/`role` manifest fields. Exact suffixes and physical folder layouts are unnecessary.
- Index every prepared PDF page, highlight quotations and typed annotation comments, plus saved Notable transcripts. A transcript-only correction refreshes the text index without uploading the PDF again.
- Detect a later native PDF-only index rebuild and restore the added annotation/transcript text on the next publication run, without uploading an unchanged PDF.

The companion does not write Zotero's SQLite database, contact a tablet account, or start at Windows login. All network requests are restricted to the selected localhost API; the upstream file-upload step is guarded separately. Local API credentials remain in memory and are not printed or stored in manifests/state.

## What “search handwritten notes” means here

Notable already searches saved handwriting transcriptions and has optional isolated-ink OCR. That feature is preserved as **saved text**, not misrepresented as a new reliable recognizer. No OCR engine runs merely because the companion publishes a paper. Ink remains in the annotated PDF; its automatically suggested or corrected transcript is searchable when present in the selected source data.

This pilot adds annotation text to Zotero's **Attachment Content / Everything** index. It does **not yet** create native Zotero annotation objects or separate highlight-only/comment-only filters. A search can retrieve a paper from its annotation text, but PDF Find cannot necessarily highlight an index-only transcript on the ink. Native annotation-specific filters, text/image close-ups and links to individual notes remain further integration work. Typed annotation replies/comments are carried as the PDF/stored-source text available to the existing extraction pipeline; no exhaustive claim about every PDF reply format is made.

Pages without a printed text layer are reported during indexing. General printed OCR preprocessing and new handwriting recognition are not part of this publisher. Adding an existing OCR component remains planned; the earlier OCR experiment does not make it an implemented automatic feature.

## Dependency choice and reuse

The existing open-source survey and executable preflights were consulted before implementation:

- [Pyzotero 1.16.0](https://github.com/urschrei/pyzotero/tree/v1.16.0), BlueOak-1.0.0, supplies the local API client and complete file-upload protocol. This implementation adds a localhost URL guard around its public `Zupload` class; it does not reimplement that protocol. Its overridden upload hook is an upstream implementation detail and must be rechecked before changing the pinned Pyzotero version.
- [Official Zotero local API](https://www.zotero.org/support/dev/web_api/v3/local_api) supplies instance IDs, versioned records, explicit local authorization and full-text writes. Zotero 10 is required for writes.
- Existing Notable `combined_pdf`, `remarkable_sources`, `extraction` and protected publication routines supply source verification, rendering and quotation extraction. They remain available to the standalone app.
- Runtime direct dependencies are only PyMuPDF, Pillow, rmscene and Pyzotero, pinned in `requirements-zotero-pilot.txt`; the companion does not require the Tk/WebView2/Office/AI stack. Existing component license obligations remain applicable.

The current released reMarkable Zotero plugin did not pass the Zotero 10 compatibility preflight. This is why a focused companion is being tested rather than assuming that an existing released plugin already completes this workflow. See the [route decision and source comparisons](research/2026-10-18-triage-and-route-decision.md).

## Developer use

Use a separate Python 3.13 environment and a separate Zotero 10 test profile/library. This has not upgraded the PC's installed Zotero 9 or imported the real literature library.

```powershell
py -3.13 -m venv .test-tmp/zotero-pilot-env
.test-tmp/zotero-pilot-env/Scripts/python.exe -m pip install -r requirements-zotero-pilot.txt
```

Enable Zotero's local API in its test-profile Advanced settings. Normal write permission is granted by Zotero's own dialog; choose **Always Allow** for a multi-request publication. Keys stay in memory in this initial command-line pilot; a new invocation may ask again. Revocation, one-time-key expiry or a closed Zotero process stops the run and preserves its retry state. Quiet credential persistence/reconnection is not yet implemented.

Prepare one paper selected by its existing logical paper UUID. `--metadata` is optional JSON with native bibliographic fields, for example `itemType`, `title`, `university` and `thesisType`. The pilot does not guess a thesis degree or overwrite an existing reviewed citation.

```powershell
python tools/zotero_pilot.py prepare --library "<Notable library.sqlite3>" --paper-id "<selected paper UUID>" --output ".test-tmp/selected-paper"
```

The command returns the prepared manifest path. Run a plan first; add `--apply` to publish only that selection:

```powershell
python tools/zotero_pilot.py publish "<prepared manifest.json>" --state-dir ".test-tmp/selected-paper-helper" --port 23129
python tools/zotero_pilot.py publish "<prepared manifest.json>" --state-dir ".test-tmp/selected-paper-helper" --port 23129 --apply
```

Port 23119 is the normal Zotero default; 23129 is used by the disposable integration test. Keep a state directory dedicated to one source namespace and Zotero instance. A changed prepared PDF needs a newly prepared manifest/digest. Source IDs remain stable between prepares. Existing unrelated Zotero references are not adopted by title or DOI; production matching/migration is a separate step.

Preparation uses a consistent SQLite read for saved annotation text, then existing renderer checks for the selected PDF. It is not an atomic snapshot of a simultaneously changing whole Notable library. Pause source updates during a controlled pilot. Existing-source revisions/provenance remain in the manifest and original library; the helper does not claim those are automatically aligned to every new handwriting stroke.

## Verification

The new automated tests cover preview isolation, stable keys, metadata preservation, refresh, upload/index failure recovery, independent PDF edits, deletion handling, instance binding, same-parent SI, state locking, changed inputs, annotation search fields, transcript corrections, and selected-paper-only transcript preparation.

```powershell
.venv/Scripts/python.exe -B -m unittest tests.test_zotero_pilot tests.test_combined_pdf -q
```

The real Zotero test uses the project's developer dependencies plus Pyzotero, and refuses an existing work directory. It starts a new headless profile, disables account sync and Office integration installation, verifies that the API instance ID matches its own test process, and simulates consent only inside that disposable profile:

```powershell
python tools/test_zotero_pilot_live.py --zotero-exe "<extracted Zotero 10 zotero.exe>" --work-dir ".test-tmp/new-publisher-test" --port 23129
```

The final automated run passed **62 tests**: 19 new companion tests and 43 existing combined-PDF tests. A minimal companion-only environment passed `pip check` and prepared a cached tablet paper without loading Tk, WebView, Office or Gemini modules.

Successful Zotero 10.0.6 trial `.test-tmp/zotero-publisher-live-08/results.json` records nine passed checks; a retained copy is in [the implementation results](research/2026-10-18-zotero-pilot-results.json):

1. Preview left Zotero empty and the selected Notable database unchanged.
2. An annotated PDF and typed Thesis metadata were published.
3. Highlight text, typed comments and a saved handwriting transcript entered the index and retrieved the paper through Zotero library searches.
4. Repeating the run retained one attachment and the title edited in Zotero.
5. A newer synthetic tablet scene refreshed the same attachment, now containing three marks.
6. The previous prepared version and original source remained available.
7. Search retrieved the final-page marker of a 125-page, 700,020-character synthetic thesis.
8. A printed-text-only index replacement was repaired without uploading the unchanged annotated PDF.
9. Transcript retrieval and the long-thesis final-page search survived a real Zotero shutdown/restart.

This is a real local Zotero/API test with synthetic cached reMarkable scenes. It is not a live-device, handwriting-accuracy, interactive-reader-refresh or unattended-service test. Early test iterations exposed and corrected SQLite handle cleanup, the API's requirement for `version: 0` on stable-key creation, and repeated consent requests within one process. A later test assertion accidentally reused its earlier prepared snapshot; it was corrected to exercise the current PDF revision. Failed attempts remain under their separate ignored test directories and are not counted as passed checks.

## Next implementation gates

1. A small setup/status surface and quiet lifecycle/credential handling. Decide whether a thin plugin or existing Zotero controls provide the simplest daily use.
2. Explicit mapping/adoption of existing Zotero references and reMarkable IDs; collection/folder correspondence and new PDF additions in both directions. The current publisher handles only prepared Notable-to-Zotero outputs.
3. Native Zotero annotation objects/filtered notes, source links and conflict handling for independent Zotero annotation edits or changed page geometry. Current PDF bytes and reference metadata checks do not validate every database-only annotation interaction.
4. A real tablet trial in a dedicated subtree: actual ink/highlights, repeated refresh, offline/restart recovery, no duplicates and no unwanted PC annotations sent to the tablet.
5. Printed OCR integration and measured scientific handwriting retrieval. Preserve saved transcripts and original ink while evaluating recognizers.

The current implementation is useful evidence and a reusable component. It is not grounds for retiring Notable or migrating the production library yet.
