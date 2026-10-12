# Combined workflow tooltip audit

October 8 follow-up: the current path design uses full current paths together
with contextual hover help and compact copy buttons throughout the interface.
There are no separate path right-click menus. Table help includes actual paths
even when the displayed filename fits. Known paths in text panels have the
same hover treatment; long tooltips can widen within the active monitor.
Filename help follows draft edits. Empty locations disable copying, and
personal keys and pairing codes never receive path controls. The full current
suite passed all 649 tests; see `tmp/consistency-full-tests-final.log` and the
latest section of `AUDIT.md` for coverage and manual-check limits.

Completed October 7, 2026 using source inspection, isolated Tk controls,
synthetic libraries, and the computer-use skill for visual layout inspection.
No account, credentials, or real research documents were used in UI checks.

Reviewed Inbox, Library, Notes, reMarkable, Settings, duplicate review, transfer
queue, processing dialogs, and menus. Existing hover behavior tests cover
disabled controls, focus/tab changes, dismissal, clipped cells and popup reuse.

Changes:

- Every Sorting entry, selector and switch now explains its purpose and
  relevant limits. Naming styles and templates give concrete examples.
- DOI lookup explains identifier-only traffic. Optional Gemini identifies
  document-text use, personal keys, default-off behavior, and separate DOCX and
  PPTX permissions. Legacy PPT remains local.
- Remove saved key stages deletion, with saved/not-saved and pending-removal
  status. Undo removal, Cancel, or closing Settings preserves the stored key.
  Save commits deletion and disables Gemini; using Gemini later requires
  entering a key again. Blank input normally preserves a saved key.
- Inbox status hints explain completed downloads, waiting, review, skipping
  and errors. Retry, file collision rules and PDF-only note processing are clear.
- Cloud services, PDF sending and each mirror direction have separate help,
  including disabled choices. Settings explains when drafts take effect.
- Refresh folders discloses enabled mirroring side effects; Sync PDFs describes
  downloads and enabled queues. Automatic PDF checks and the cloud master
  switch explain their different scopes.
- Duplicate review explains cached-data uncertainty, comparison scope,
  confirmed linking, previously linked variants, source/history preservation,
  mapping, and explicit transfers. No-match results do not prove absence.
- Show/Hide action tooltips follow the current button label. Annotation history
  refers to the selected note's actual PDF source. Processing help distinguishes
  drawings from highlights and typed comments.
- Settings remains compact; Sorting scrolls while Save and Cancel stay visible.

Automated acceptance coverage is in `tests/test_workflow_tooltips.py`, existing
`tests/test_tooltip_behavior.py` and the application button/dialog audits.
`tests/test_combined_workflow_ui.py` additionally covers key-removal Save/Cancel
behavior, captured Settings choices, retries, stale reviews and non-PDF boundaries.
After the staged key-removal update, 76 targeted workflow, Settings, tooltip,
and Inbox tests passed, including Undo and failed-Save preservation.

Previous complete regression run, before the staged key-removal change: 489
tests passed. Source compilation and Git whitespace checks also passed. Live
naming/transfer behavior still needs the agreed small pilot before replacing
the old sorter's normal workflow.
