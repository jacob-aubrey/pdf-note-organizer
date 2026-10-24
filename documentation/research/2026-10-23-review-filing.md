# Clear folder names, supporting information, and queued review filing

## Reuse decision

The folder-label correction reuses the saved folder mappings and native HTML
select controls. It changes neither folder identities nor sync relationships.
Current catalog names take precedence, with saved names available offline.

For supplements, reuse Zotero's existing regular reference plus child attachment
model, documented in [Adding files](https://www.zotero.org/support/attaching_files).
There is no new native bibliographic type. Supporting Information is a plugin
review choice: the user selects the main reference, and the file becomes its
child attachment. The existing local API, publication ledger, and PDF renderer
are reused. The main citation is not renamed or retyped. Old references are
retained when an existing attachment is reassigned. No merge or delete occurs.
The upstream [Zotero repository](https://github.com/zotero/zotero) is maintained,
and its [licensing](https://www.zotero.org/support/licensing) is AGPLv3 unless a
file states otherwise. This is an integration with the already-installed
Windows Zotero 10.0.6, not copied upstream implementation code. The behavior
is tested against that version; upstream documentation alone is not proof of
the complete plugin workflow or of another reMarkable device/firmware version.

The worker already serializes requests with Python's standard-library
queue.Queue. Reuse it, the controller's existing action/RPC mechanism, and
content-bound approval checks. A frontend journal lets the user submit reviews
while work proceeds without concurrent writers. The journal uses Gecko's
existing IOUtils.writeUTF8 with tmpPath for atomic replacement, documented in
the maintained [IOUtils interface](https://searchfox.org/firefox-main/source/dom/chrome-webidl/IOUtils.webidl).
The Mozilla source is MPL-2.0; only its built-in API is called. No source or
runtime dependency is imported from Mozilla by this change.

[p-queue](https://github.com/sindresorhus/p-queue) was considered. Its actual
API supports concurrency=1, pause/resume, and queued promise execution. It is
[MIT licensed](https://github.com/sindresorhus/p-queue/blob/main/license),
native ESM, and described by its maintainers as feature complete. It supplies
no durable approval journal, native reference handling, or plugin connection
isolation. There is no demonstrated Zotero 10 integration or Windows/device
compatibility in its README. Adding its dependencies and ESM packaging would
duplicate the existing serialized transport. A small adaptation of the current
controller is appropriate and requires no additional user setup.

## Behavior

- Batch, individual, and move destination menus identify both Zotero and
  reMarkable paths. Two wrapping lines below the menu keep both names visible.
- SI review requires an explicitly selected live main reference. Its citation
  snapshot is checked again before filing; tag/version-only changes do not
  invalidate an otherwise unchanged citation. Existing PDF-match checks apply.
- Review fields remain editable while other work runs. Approvals capture the
  selected filename, destination, match, main reference, and review token.
- Jobs are saved atomically before execution, scoped to the selected folder
  connection, and processed one at a time. Duplicate clicks do not enqueue
  the same review twice. A queued job can be removed before it starts.
- Re-rendering retains the next paper's unsent form edits for the same source
  digest. A changed source starts a new draft instead.
- A failure or Stop pauses remaining jobs. Restarted Zotero shows saved jobs
  and requires Resume queued filings. No queued work starts merely on opening.
- Manual review filing requests one annotation sync after queued approvals.
  Batch approval retains its existing explicit Sync now workflow.

## Validation

Results and exact package hashes accompany the 0.6.0 release. Development and
packaged native checks use disposable profiles, synthetic references, and an
in-memory cloud. Production Zotero and the user's tablet are not changed.

The related Python suites passed 98 tests. The controller's scheduler and
delayed-response filing-queue checks passed. The exact XPI and bundled helper
passed 11 native review checks: native SI attachment reassignment/renaming,
preserved citation/PDF/previous reference, native main-paper search, editable
review during a batch, saved choices, serialized execution, captured citation,
and unsent draft retention through completion and annotation sync. Eleven
additional packaged checks covered saved-path fallback, all affected views in
light/dark/narrow layouts, and native menu selection preserving identity keys.
Screenshots were inspected. A separate packaged restart check verified saved
jobs reappear paused and do not start merely when the plugin reopens.

Evidence: `.test-tmp/zotero-060-packaged/review-native-results.json`,
`folder-ui-results.json`, and `queue-restart-results.json`; supplementary
development activity checks are under `.test-tmp/zotero-060-dev`.
The first sandboxed native launch could not initialize Zotero; the successful
native runs used the normal Windows process environment and scoped test data.
Initial Python tests also required a workspace-local temporary directory;
permission errors from the sandbox's default temp directory are not counted as
passing tests. No production plugin installation or real-cloud transfer occurred.
