# Responsive workspace and review preview: 0.4.2

## Reuse and scope

The previous timer ran an automatic cloud sync every minute even while the
workspace was open. All buttons were disabled during that operation, so a user
could neither start a Windows scan nor inspect the reviews. Cloud intake also
rebuilt unchanged pending proposals repeatedly, including local text extraction.
The UI's single progress sentence did not show duration or activity clearly.

This is a targeted repair of the existing scheduler, review cache, and UI.
There is no replacement scheduler, control library, reader, or sync engine.
The existing JSON progress channel, HTML progress element, CSS animation,
SQLite review state, and cancel transport cover the requirements. Browser
reduced-motion preferences suppress spinner animation. Real file counts are
used only when the worker reports them; other steps have an indeterminate bar.

For opening papers before import, reuse the installed Zotero 10.0.6
`Zotero.launchFile` API. Its actual implementation in
`app/omni.ja:chrome/content/zotero/xpcom/zotero.js` was inspected: it accepts a
local path/nsIFile, uses the platform file launcher, and has platform fallbacks.
This avoids creating temporary library attachments or adding a separate PDF
reader. The local file must exist, have an absolute path, and use one of the
already-supported PDF/Word/PowerPoint extensions. Native attachment readers
remain in use for existing Zotero page/tag navigation.

Zotero's upstream project is AGPL-3.0-or-later; only its installed API is called,
and no source is copied into the plugin. The selected runtime is the existing
Windows x64 Zotero 10.0.6, whose native APIs and UI are tested here. A repository
compatibility claim is not used as evidence for other application versions or
operating systems. This small adaptation requires no additional dependency,
duplicate user document, account, or recurring setup. Earlier upstream
integration alternatives remain recorded in the folder-connection reuse record.

## Behavior

- Automatic checks wait while the workspace is open, including Import library,
  Review, and Setup. Timer callbacks recheck this condition to cover races.
  Opening the workspace cancels a running automatic check at a normal stop
  point. The saved automatic-sync preference and durable pause flag do not change.
- Automatic checks resume after closing the workspace, normally after five
  minutes. Error backoff increases that delay up to fifteen minutes. Manual
  Sync now remains available while the workspace is open.
- Navigation, review selection, routine-paper browsing, and Open paper remain
  available while a job runs. Mutation controls wait until it finishes.
- A distinct activity panel shows a spinner, job name, current file/step,
  progress count where known, elapsed duration, and time since a quiet update.
  It survives navigation and clears on completion. One Stop/Pause button
  replaces duplicate Stop and Pause controls with the same function.
- Unchanged pending cloud reviews reuse the verified incoming PDF and proposal.
  Current cloud revision, cached file bytes, paper name, and naming templates
  determine reuse. Desktop match suggestions still refresh against the current
  native catalog. Changed or missing input is re-read; modified retained PDFs
  are preserved and block reuse instead of silently replacing them.
- Windows scans report every file, including duplicate copies, against the
  discovered total. Existing content grouping and exception review remain.
- Open paper calls the local launcher directly, so it does not wait behind a
  sync request or approve/import anything. New tablet reviews open the original
  cached PDF; rendering handwriting remains in the approved sync path. Browse
  all papers exposes routine records as well as exceptions.
- Oxford commas are used in plugin UI lists and the current setup guide.

## Validation

The related Python suite passed 94 tests, including cache reuse with refreshed
desktop matches, naming/template invalidation, modified-file retention,
cancellation before another extraction, and per-file scan counts with duplicates.
The scheduler's JavaScript checks passed timer/window races, busy/paused guards,
temporary cancellation, retained preferences, and retry backoff.

The exact XPI passed 19 native/package checks on Windows Zotero 10.0.6. Eight
exercise the new UI behavior: automatic checks wait while open, navigation
works during a scan, counts and elapsed time appear, Open paper passes the
existing local file to Zotero's launcher without RPC/approval/import, routine
papers can be browsed, the activity panel clears, automatic work yields, and
automatic checks resume after closing. The OS launcher is intercepted in the
fixture to avoid opening an external application during automated testing;
the real file validation and native file object are exercised. The remaining
checks cover folder safety, restoration, disconnect, OCR, and native search.

Thirty UI/native-menu checks passed: five tabs in light/dark at 1040px and dark
at 640px, folder confirmations, three real native pickers, and six active-job
views. Screenshots of the activity panel and Open paper action were inspected.
The final helper also returned all 140 records from the retained Unicode queue.
The XPI's frontend entries match the final source bytes.

Evidence is under `.test-tmp/zotero-042-native-01`,
`.test-tmp/zotero-042-unit-results.json`, `tools/test_zotero_scheduler.cjs`,
and the release metadata beside the XPI. Tests use disposable profiles and
synthetic cloud documents. No real-library import, cloud transfer, connection
change, or production installation is part of release validation.
