# October 26 sync stoppage investigation

**Installed 0.9.4 and completed two real configured syncs.** Durable evidence demonstrated two defects: incomplete runtime packaging prevented startup, and expensive native PDF saving starved the heartbeat until the parent terminated the helper. Both are repaired. The repeat sync made **zero Zotero item/version changes**, rendered/indexed/uploaded no content, and left saved identities, receipts, reviews and configuration unchanged.

This is the requested midnight diagnostic continuation, reusing the October 25 full audits. It is **not a new whole-tree audit or a claim that every device/format works**. Started October 26, 2026, 00:01 EDT / 04:01 UTC, America/New_York. Initial revision `2f06ac2bed28a569bed56a64f8ceccb47f2e886e`, branch `main`, no pre-existing tracked changes. Changed-range coverage and source hashes are in `change-review-ledger.json`; the verified source commit is recorded in `CHANGESET.md`. Source references below are repository-relative.

## Demonstrated causes and repairs

**P1 — Native PDF save blocked normal sync.** Instrumented 0.9.1 reached paper 254/454, tablet key `8abc6c7a-1265-56b9-be1a-45d838095af1`, at **01:23:54 EDT / 05:23:54 UTC**. Last heartbeat:05:23:57.910 UTC. The process remained alive and consumed a CPU core; both Python heartbeat and stack-sampler threads stopped advancing. Two independent external stack-only samples located the active GIL-owning main thread at `pdf_write_document → save → tobytes → remarkable_pdf._annotated_pdf:450` (frozen091 lines), not the stale internal socket-read snapshot. CPU increased95.99 seconds over97.8 wall seconds with identical I/O counts.

At **01:33:57.915 EDT / 05:33:57.915 UTC**, the frontend recorded inactivity timeout, parent termination request/kill, EOF, then exit **-9**, `parent_initiated:true`. Exact UI error: **“The helper stopped responding and was stopped safely. Retry your action to restart it.”** This run ended by parent termination, not a native crash. See `first-sync-stopping-timeline.json`, `stall-live-stack-*.txt`, `stall-cpu-summary.json`.

The 541-page, 22,342,650-byte source triggered `tobytes(garbage=4, deflate=True)` global object/stream deduplication. A private immutable copy reproduced the costly save; retaining the graft map alone and level3 compaction were insufficient. The repair reuses the page-copy resource map and uses level2 compaction (`note_organizer/remarkable_pdf.py:499`, `:532`). Exact copy completed in 12.279 seconds including navigation repair; all 541 pages matched pixels at 36 dpi, text and geometry, with equivalent links within 0.01 point and 181 bookmarks preserved (`pdf-save-copy-verification.json`). On the repaired live093 run, this same document's native save took **1,239ms** (`live-093-former-stall-document.json`). Both final094 runs passed it; repeat reused its verified cache.

**P1 — Incomplete frozen dependency bundle prevented startup.** Actual installed version at entry was **0.9.0**, not an assumed0.8.8. XPI, cached/running helper, frontend and all 36 first-party Python modules matched their package/source. The frozen archive nevertheless lacked **pyzotero/httpx2/httpcore2**, also optional OCR dependencies. Latest saved error at October26 **03:57:28 UTC** was `PilotError: Install requirements-zotero-pilot.txt in a separate environment.`, at opening connections, before any transfer. The earlier reported handwriting message is distinct. Frozen disassembly and transport proved Sync dispatched `sync` and called `self.zotero()` without OCR; stale code/cache or a reindex command was not the demonstrated cause (`initial-*.json`, sync disassemblies).

Build preflight and exact-frozen-helper `runtime_health` now gate releases (`tools/build_zotero_support.py:12`, `:24`, `:84`, `Notable Zotero Worker.spec:7`). Missing-runtime errors identify installation repair. Ordinary Sync remains independent of handwriting OCR (`note_organizer/zotero_worker.py:988`). The historical bad build command/environment is not established.

**P2 — Navigation loss found during preservation verification.** Page copying omitted document-level named destinations. Resolved names now become explicit page destinations, with native/display coordinate conversion. Already unresolved source targets stay unresolved, without inventing pages or blocking publication; escaped parentheses, backslashes and Unicode are retained (`remarkable_pdf.py:271`). All26 initially held immutable source copies passed printed-text/unresolved-target equality, plus focused synthetic link/bookmark checks (`unresolved-navigation-copy-verification.json`). Render revision 6 rebuilds derived views once. Originals/tablet layers stay retained. The initial 093 guard was corrected in 094; earlier failing comparisons remain evidence.

**P2 — Diagnostic causality and privacy gaps repaired.** Existing OperationTrace, Mozilla process APIs and HTTP send boundaries were extended, not replaced. Records identify correlation, UTC/elapsed times, stages/pages/database work, request outcomes/timeouts/retries, sent/received heartbeats, active/completed operations, executable identity, parent termination, cancellation/pause, EOF/invalid protocol, exit code and safe exception frames. Dynamic private error text was caught and removed before final release. Primary locations: `zotero_worker.py:66`, `:1715`; `zotero_pilot.py:278`; `zotero-support/ui.js:63`, `:128`, `:215`, `:227`, `:249`, `:288`. Logging failures do not change sync outcomes. JSON stdout remains protocol-only; stderr retains bounded structural flags/types/modules, not raw document text. The unsafe native timed traceback watchdog remains disabled.

These facts establish this startup failure and captured live stop. They do **not** prove every historical stoppage or the earlier Python 3.13.1 crash had these causes. A successful restart alone was not used as proof.

## Exact installed build and preservation

| Item | Verified value |
| --- | --- |
| Application | Zotero **10.0.6**, Windows; stale Windows app identifier says 9.0.1 |
| Final XPI | `dist/reMarkable-Sync-for-Zotero-0.9.4.xpi` |
| XPI SHA-256 | `93874ae6bc1d05b8cc5aa552a6452d0a2c318a831e88bf6d09e9345de7f34416` |
| Helper SHA-256 | `72777e251921651516c6589642e68ae278e547fd203d04bc00f1f07f6d307ce2` |
| Runtime manifest ID | `69877b7770a966915ba52021` |
| Manifest executable MD5 | `63913efa5ec7d446283d4f6a4c5b73f8` |
| Real profile | `%APPDATA%/Zotero/Zotero/Profiles/9v5afvrs.default` |
| Installed extension | `extensions/notable-companion@local.invalid.xpi` under that profile |
| Actual cached helper | `notable/runtime/69877b7770a966915ba52021/notable-worker.exe` |

`package-094-verification.json` proves all 36 frozen application modules, entrypoint, 31 frontend/assets, helper bytes/manifest and six required plus three optional imports match the reviewed build. `installed-094-verification.json`, `loaded-094-*.json` verify the active real profile, frontend, endpoint version, executable paths and hashes. The same parent 41052/worker 6808 processes survived both final runs; post-repeat process/hash evidence is retained. Source hashes were rechecked after acceptance preparation: no application module changed since the build.

The 093 hot install initially failed with **NS_ERROR_FILE_IS_LOCKED**, specifically moving the old XPI to extension trash (`installation093-error-console.txt`); compatibility was not the proven cause. Supported recovery worked: **disable plugin → normally quit/reopen Zotero → Install Plugin From File while inactive → enable**. The same workflow installed 094. No direct unsupported profile replacement was used.

Before any replacement, 22 initial package/settings/state/log files, encrypted grants, actual old helper and failure artifacts were preserved under ignored `.test-tmp/sync-diagnostics-20261026/initial/`, with hashes in `initial-installation.json`; logs also in `pre-update-logs/`. After normal shutdown, each supported backup below passed **16 files/eight SQLite integrity checks**:

- `.test-tmp/full-audit-20261025/pre-091-midnight-backup-complete/` — original installation/state.
- `.../pre-093-midnight-backup-complete/` — interrupted 091 state.
- `.../pre-094-midnight-backup-complete/` — completed 093 state and previous 093 XPI.

Rollback installs the desired `previous-plugin.xpi` through the same supported inactive workflow. Preserve current state and backups before any database restoration; never substitute a fixture library. Immutable source/cache/model files were intentionally excluded from these package/database backups and remain retained in-place. All 310 old derived-view files referenced by the pre-093 backup were SHA-verified still available (`rollback-rendered-cache-verification.json`). Prior audits, original research files, grants, mapping roots, review choices and per-link pauses were preserved. No ambiguous content, reference, folder, deletion or replacement decision was made.

## Production acceptance

Used actual workspace **Sync now**, existing saved grants, folder mappings and approvals. The workspace remained open so automatic checks could not race the acceptance comparisons.

| Observed run | Result |
| --- | --- |
| 091,01:07:41–01:33:57 EDT /05:07:41–05:33:57 UTC | Reproduced captured save starvation/parent timeout; did not complete. |
| 093,02:00:47–02:51:57 EDT /06:00:47–06:51:57 UTC | Completed, former failing save 1,239 ms. Navigation guard still needed correction; not final acceptance. 092 was tested but never production installed. |
| **094 first**,03:11:32–03:31:47 EDT /07:11:32–07:31:47 UTC | Reached final paper ordinal 454; 453 publication actions, 66 per-run review entries, zero partial indexes; normal completed RPC. 62 necessary renders/64 indexes, 80 heartbeat receipts; no trace failure/timeout/retry/parent kill. |
| **094 repeat**,03:33:36–03:47:35 EDT /07:33:36–07:47:35 UTC | Reached final paper ordinal 454; 453 unchanged publication actions, 66 review entries, zero partial indexes; normal completed RPC. **Zero renders/indexes/content uploads**, 55 heartbeat receipts, no failure/timeout/termination. |

Correlations: first `mvox2c95-ifhz4kl9j9-3`; repeat `mvox2c95-ifhz4kl9j9-4`. Structural timelines: `live-run-094-first.json`, `live-run-094-repeat.json`. Action counts include unchanged publications and are **not new-transfer counts**. Existing paused/held cases remain below; completion does not mean every review-dependent document was transferred.

Repeat acceptance (`repeat-state-post094repeat.json`, `native-versions-post094repeat.json`):

- **Zero added/removed/changed mappings or publication receipts**, including source/view identities, baseline/render/index/page-map hashes and tag state. Review database and configuration hashes unchanged. Selected-state SHA-256 identical: `fd0c87f134e9b79d67539c602e23f996c47045e04fbab90fb7150e8a197ab264`.
- **Zero added/removed native item keys and zero changed native item versions** across 3941 API-visible items. First 094's eight new native identities were all annotations under existing managed views, not duplicate source references (`native-versions-first-additions.json`). Raw database 4949-item earlier snapshots use a different scope and are not compared to API totals.
- Repeat issued 6474 native GETs and two POST `/api/notable/action` catalog operations; cloud POST was existing authentication, with 15 GETs and no PUTs. No file upload, fulltext update, annotation refresh or item PATCH occurred.
- Final state: 456 mappings, 454 uploaded, 454 managed views, 453 received revisions; zero duplicate source/view groups, zero pending publication MD5s/upload intents/tag recoveries, all present inspected databases integrity-OK. 453 retained source manifests match identity/baseline/self-hash with baseline/layer files present. 13 latest-metadata/source-revision differences have completed tag state and retained history, not missing source proof (`post094repeat-state.json`).

Read-only live cloud checks found **454/454 uploaded identities active, 454/454 original PDF digests matching**. Three fresh remote originals matched SHA-256; three actual local managed PDFs matched publication MD5 (`live-preservation.json`). These are all-identity metadata checks plus byte samples, not whole-library/device pixel comparisons.

Actual final UI: **“Sync finished — some links need attention”**, 57 need review, 3 approved waiting for sync, 456 linked. The same reviews remain after repeat. Per-run 66 review entries and persistent 57 pending rows describe different sets; they must not be summed or relabeled as 66 runtime failures.

## Checks, reuse and diagnostic retention

**287 final source regression tests passed** in 255.281 s; seven focused PDF/navigation/repair checks passed. All six JS controller suites passed. Exact 094 frozen native baseline: **14 passed**, plus actual explicit OCR/reindex, malformed-PDF stderr/valid following JSON, unchanged synthetic bytes and exit 0. Broader 53 native/30 rendered-UI checks ran on earlier candidates and are reused only for unchanged behavior; counts overlap and are not summed or relabeled as 094. Final syntax/compile/diff checks passed. See `DIAGNOSTIC_MATRIX.md` for every requested failure/control path, and `COMMANDS.md` for commands, versions, results and superseded candidates. Earlier fixture failures and failed preservation comparisons remain clearly labeled.

Adapted existing APIs: [Mozilla Subprocess](https://firefox-source-docs.mozilla.org/toolkit/modules/subprocess/toolkit_modules/subprocess/index.html), [IOUtils](https://raw.githubusercontent.com/mozilla/gecko-dev/master/dom/chrome-webidl/IOUtils.webidl), [HTTPX hooks](https://www.python-httpx.org/advanced/event-hooks/), [PyMuPDF insert/save](https://pymupdf.readthedocs.io/en/latest/document.html). Actual native IOUtils rotation, process lifecycle and timeout extensions were exercised. Retained pinned Pyzotero 1.16.0 (BlueOak-1.0.0), httpx2 2.14.0 (BSD-3-Clause), PyMuPDF 1.28.2 (AGPL/commercial), RapidOCR 3.10.0 (Apache-2.0), ONNX Runtime 1.31.0 (MIT), PyInstaller 6.22.3 (GPL/bootloader exception). Metadata provided versions/licenses; exact frozen tests establish current Windows/Zotero compatibility. This is no new distribution-license approval or claim of every future version's support.

Audit-only [py-spy 0.4.2](https://github.com/benfred/py-spy/releases/tag/v0.4.2), [MIT](https://github.com/benfred/py-spy/blob/master/LICENSE), supports Windows/CPython 3.13 and actually read the frozen 3.13.1 stack. It was extracted privately, not added to plugin dependencies; no locals/memory dump (`py-spy-provenance.json`). Reuse avoided a new logger, renderer or process architecture. Generated archives, binary libraries/models and vendored dependencies are provenance/version/import checked, **not manually line-reviewed**.

Profile logs `notable/sync-trace.jsonl` and `sync-transport.jsonl` each retain current+`.1`+`.2`, at most 2 MiB each; append/flush, Python also fsync. Optional safe Python stack snapshots rotate similarly, with a single-snapshot threshold overshoot possible. Supplemental private `*live-timeline.jsonl*` captures are three 16 MiB files per capture; successful DB spans excluded only from this supplement. Collectors were explicitly stopped and final profile logs copied into private `live094first-finished/` and `live094repeat-finished/`; earlier stalled captures remain. **Copy all rotations after a future failure before restart/update.** Disk/permission failure can still lose a best-effort diagnostic record. Secrets, authorization headers, signed URLs, request bodies, PDF/annotation text and arbitrary stderr are excluded. Public artifacts were checked against saved grant values without exposing them.

## Remaining limits and required choices

1. **External account blocker confirmed:** actual Zotero popup says **file-storage quota reached; some files were not uploaded**, while other metadata can sync (`zotero-account-warning.json`). This is separate from the repaired plugin stop. Account attachment delivery to a second computer remains unverified until the user resolves storage; no subscription/settings/file changes were made.
2. **Existing decisions preserved:** 57 pending review rows; 3 approved unlinked PDFs are exact-content duplicates of already connected tablet PDFs and need reference/home reconciliation. Two staged papers remain individually paused; three link controls are paused, zero eligible staged uploads. Existing bulk import remains 486 complete/87 pending with 90 issue-bearing rows. No new bulk import or ambiguous decision was authorized or performed.
3. **Four PDFs need text recognition/manual keyword tags** (`keyword-review-status.json`). Ordinary Sync does not require or invoke handwriting OCR. Explicit OCR/reindex works on disposable final-runtime fixtures; it was not forced on research documents.
4. Source-unresolved navigation stays unresolved. Offline clones emitted rmscene's newer/unread-format warning; original tablet bundles remain retained. No physical tablet pen-stroke/firmware comparison, new device annotation or second-computer attachment round trip was performed. Live metadata/PDF samples and synthetic annotation tests cannot prove every visible ink stroke or format.
5. The earlier native Python crash and every historical stoppage are not retroactively diagnosed. Installed bounded instrumentation remains available for future evidence. Current two-run completion is strong evidence for this configured workflow, not a guarantee of flawless operation.

Final evidence recorded: 2026-10-26T07:50:45.077261+00:00 (UTC); local timezone America/New_York.
