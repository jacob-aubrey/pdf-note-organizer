# Paper and page tag integration

The user approved two-way whole-paper and page tags, including publisher keywords,
on October 22, 2026. Page tags must not become reference tags automatically.

## Existing implementations checked first

- Zotero's documented [reader extension events](https://www.zotero.org/support/dev/zotero_7_for_developers#custom_reader_event_handlers)
  provide `renderToolbar` injection. Reuse that event for the page-tag control,
  native `Reader.open`/navigation for page links, native reference tags for
  whole-paper labels, and the existing plugin/worker transport and state store.
  The actual installed **Zotero 10.0.6 Windows x64** `app/omni.ja` was inspected:
  reader `itemID`, active primary/secondary `ViewStats.pageIndex`, and page-index
  navigation are present. These internals are version-sensitive; the manifest
  remains limited to 10.0.x. Upstream Zotero/reader are maintained AGPL-3.0
  projects; Zotero remains installed separately, and no reader source is copied.
- [reMarkable's tag documentation](https://support.remarkable.com/articles/Knowledge/Tags)
  confirms separate document and page tags. It does not provide a supported
  public cloud write API.
- The maintained **rmapi-js 14.4.0** upstream [raw schema](https://github.com/erikbrinkman/rmapi-js/blob/main/src/raw.ts)
  defines `Tag {name, timestamp:number}` and `PageTag {name, timestamp, pageId}`.
  Its [MIT license and package](https://github.com/erikbrinkman/rmapi-js/blob/main/package.json)
  were checked. It runs in JavaScript/Node on Windows, but adding another runtime
  would duplicate the existing content-addressed cloud writer. Adapt these data
  shapes in the existing Python writer instead. This is reverse-engineered
  cloud compatibility, not an official reMarkable integration guarantee.
- [ddvk/rmapi](https://github.com/ddvk/rmapi) is an AGPL-3.0 maintained fork of the
  archived original. Its documented tag filtering concerns document tags;
  this does not establish complete two-way page-tag editing. Its CLI is not
  introduced into the user workflow.

## Why page tags use plugin metadata

Zotero supports tags on annotations, which can match the parent attachment in
library search. An annotation is not a page-level identity. Creating fake native
annotations would mix page metadata with the independent desktop notes that the
bridge must protect from tablet replacement. The small page-tag adapter therefore
uses existing bridge state keyed by tablet page UUID and the ordinary cloud
`pageTags` field. No marks are added to the PDF. A clearly scoped Tags view searches
pages; the native selector continues to search whole-paper tags. This distinction
is documented rather than claiming native Advanced Search indexes private state.

## Reconciliation and preservation

First contact unions labels. Later changes use a common baseline; removals on
either side propagate, and distinct simultaneous additions combine. A rename is
removal plus addition. Automatic publisher keyword types remain intact in Zotero.
An explicit pending journal records intended/observed sets before writes, so a
successful desktop write followed by a cloud failure can recover after restart.
Ambiguous edits during interruption require a visible combine-current-copies
decision. Legacy page-to-reference promotion is flagged instead of guessing.

The existing cloud root CAS updates `.content` and `.metadata` only, retaining
unknown fields and timestamp/extension fields on retained tags. New timestamps
are numeric milliseconds. Unknown target pages and stale item revisions fail
closed. PDF and `.rm` bytes remain identical. Rendering fingerprints exclude
only document metadata and the two tag fields; other content changes still
invalidate rendering. Current reader page maps are bound to the rendered PDF's
SHA-256, and page editor/search actions validate that binding.

## Native imported-file upload compatibility

Testing revealed Zotero 10.0.6's local JSON API exposes a computed attachment MD5
while upload If-Match compares `attachmentSyncedHash`. A normal native import has
bytes but no synced hash. The adapter verifies the current managed PDF digest,
sets only that native metadata property, and retains the existing SDK upload and
CAS flow. The first tablet update now exercises an actual native import, not
only an attachment previously created through the upload API.

## Acceptance results

- 341 distinct automated tests passed: 318 plugin/cloud/OCR/intake/naming tests
  in the bundled-runtime development environment, 21 legacy citation/AI-mock
  tests in the existing full application environment, and two additional reuse/
  slow-import recovery tests added after the broad run. The AI dependency is
  deliberately absent from the plugin runtime, so those legacy tests use the
  environment that contains it.
- The final XPI passed all 25 native acceptance checks on Zotero 10.0.6 Windows
  (`.test-tmp/zotero-plugin-03-release-13/results.json`). These include actual
  reader-button/editor events, page-UUID dispatch, paper/page cloud protocol
  writes, preservation of PDF bytes, normal native imports, DOI metadata,
  deletion choices, and the bundled helper searching the saved physical-tablet
  handwriting, an image-only scan, highlights and native typed comments.
- Three reversible live-cloud checks passed on the previously recorded
  synthetic PC fixture (`.test-tmp/zotero-tags-cloud-2026-10-22/results.json`).
  Paper/page tags read back correctly; the PDF/annotation sources and every
  other cloud item were unchanged. Initial synthetic tags were restored.
- Native 500-paper intake testing exposed a slow native import and an empty
  reference left by an earlier interrupted build. Recovery/rescan matched all
  500 original PDFs, preserved the existing reference-only record, and created
  no duplicate PDFs. Native fallback parent creation/attachment assignment now
  shares one Zotero database transaction. The processing deadline pauses a
  saved batch instead of treating a readable PDF as defective. This is tested
  resumability, not a claim that every 500-file lookup finishes in one pass.
- The compiled worker's six changed modules were compared with compiled current
  source, and the XPI contains only seven frontend files, one runtime manifest
  and one executable. Runtime checksums were verified. Import and tag editor
  screenshots were visually reviewed.

No test imports production papers, flattens user folders, or changes user tags.
Physical tablet tag-menu display still needs the user's post-installation check;
the cloud data round trip is verified, not remote physical interaction.
