# Evening backend continuation

Starting revision: `7bdb3a63bf198692883286749693fca9cabcb78d`. The initial working tree was clean. The earlier audit remains historical in `documentation/audits/2026-10-25`; no product, credential, library, device, cloud, or production database was changed by this subtask.

## Coverage and changed-code review

The current backend ledger covers 65 files / 18,643 lines. Sixty-three files exactly match their earlier SHA-256 values and reuse the earlier complete source review. Two files changed:

| File | Current lines | Current SHA-256 | Evening inspection |
| --- | ---: | --- | --- |
| `note_organizer/zotero_worker.py` | 1,668 | `f3598373452fdb609a1f248160409027d4af092b9f3246523a5513c6376db83c` | Every changed range and surrounding transport/diagnostic flow reviewed |
| `tests/test_zotero_transport.py` | 147 | `b86b2a5c1e563faa1fcb6eadaaf439f3b1330b385eae39a15c614c6091b053dd` | Entire current file reviewed |

Reversing only the identified edits reconstructs each earlier file's exact audited SHA-256, accounting for the worker's CRLF and the earlier test's LF line endings. `backend-source-delta.json` records those proofs and exact changed ranges; `backend-source-delta.patch` records the functional diff. `backend-ledger.json` explicitly distinguishes reused review from evening inspection.

The worker changes permit diagnostic/transport entry points to proceed when NumPy is absent (`1589-1592`), serialize all progress/reply writes through a lock (`1618-1621,1632,1655,1664`), and emit a 15-second transport heartbeat during non-status requests with Event-based shutdown and a bounded join (`1639-1646,1660-1663`). The existing supported PyMuPDF stderr routing and safe Python stack sampler remain present. The added transport test (`tests/test_zotero_transport.py:74-98`) verifies that a 16-second request emits a heartbeat and ends with its valid result. No additional backend defect was confirmed in this changed-code review and focused verification.

## E-B1 — P2: installed 0.8.7 omits the current transport fixes

The installed and current-dist 0.8.7 XPI, SHA-256 `77166feb45d73ba972d8c35a884bac03c70b3871119d87a682df2779b4184aa1`, contains helper SHA-256 `c46095c97d64bf1ea383b26d96d4d48632eb29f828ecf831764c66b7b701c68a`. The frontend/package owner's frozen-code comparison confirms its `_serve` lacks all three later source additions: the NumPy-absent fallback, packet-write lock, and transport heartbeat. See `frontend-package087-mismatch.json` for exact packaged/source evidence. This is functional packaging drift, rather than a hash difference attributable only to line endings or build metadata.

Passing source tests therefore cannot establish that the installed 0.8.7 helper emits heartbeat activity during long requests. The parent is rebuilding the reviewed source as 0.8.8 and will require exact-package comparison and targeted native checks before installation and configured live sync. This subtask did not retry the older production helper.

## Verification and historical live limits

All **28 affected backend-repair and transport tests passed in 35.187 seconds**, including actual malformed-PDF/log isolation, conflict/filing response-loss recovery, Windows validation, PDF/staged queue counters, lifecycle checks, and the new long-request heartbeat. `py_compile` and `git diff --check` passed. The full verbose test output is `backend-affected-tests.log`.

The historical 0.8.5 native crash remains tied to the unsafe timed diagnostic stack walker and its separate native reproduction. The 0.8.6 long-run stop still has no retained offending stdout line or matching native-crash event, so its exact cause remains unproven despite the independently reproduced and repaired PyMuPDF transport leak. The historical post-0.8.6 verification found all 43 eligible staged uploads acknowledged, no missing/duplicate source/view identities or changed prior baselines, and two individually paused staged PDFs retained. Read-only cloud evidence found all 454 acknowledged identities present with matching recorded PDF digests; only three fresh remote PDF byte samples were downloaded. That evidence does not prove physical tablet download or a fresh pen-stroke round trip.

The parent reports a later pre-evening state of 309 received/indexed publications, 310 managed views, 454 uploaded mappings, two paused staged mappings, no duplicate source/view IDs, and no pending tag recovery. Those production observations and the forthcoming 0.8.8 sync/repeat belong to the parent report, not to this subtask's isolated test results. The three previously unlinked approved PDFs remain a separately diagnosed reference/home reconciliation issue: each unchanged original has an existing available tablet mapping with the exact same baseline.

Commands, from the repository root:

```powershell
$env:TEMP=(Resolve-Path tmp/backend-audit-runtime).Path
$env:TMP=$env:TEMP
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe -m unittest tests.test_zotero_audit_repairs tests.test_zotero_transport -v
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe -m py_compile note_organizer/zotero_worker.py tests/test_zotero_transport.py tests/test_zotero_audit_repairs.py
git diff --check
```

The first ledger-generation attempt used Windows' default text encoding/line-ending assumptions and failed its own reconstruction assertion; explicit UTF-8 decoding and checking the historical file's actual newline form resolved that evidence-tool issue. It was not a product/test failure, and no product file was rewritten.
