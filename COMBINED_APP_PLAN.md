# Combined literature library implementation plan

Recorded 2026-10-07. This document records the agreed direction and the staged
implementation; it does not enable syncing, alter user files, or migrate data.

## Agreed product behavior

- Run the combined app from Python and its virtual environment. Executable
  packaging is deferred.
- Bring Paper Sorter's document identification, editable naming proposals,
  filing, supported document types, and inbox watching into the existing Library
  and Notes application.
- Sorting supports PDF, DOCX, PPTX and legacy PPT. Only PDFs enter note
  extraction, consolidation, notebook generation and reMarkable paper transfers.
- A confirmed sort completes locally first. Cloud work runs through a persistent
  queue so an offline tablet or upload failure does not undo filing.
- reMarkable integration is optional and off for new installations. Enabling it
  in Settings exposes connection and folder-link setup. Individual transfer and
  folder-creation preferences remain separately configurable.
- A linked folder can send newly sorted PDFs to its tablet counterpart. Papers
  awaiting a folder link remain filed locally and display a mapping action.
- Tablet annotations return to the same paper entry and the appropriate folder's
  notebook. Ordinary local PDF notes continue to work without a tablet.
- Folder creation can propagate in both directions beneath explicitly linked
  roots. Creating a folder does not implicitly authorize a bulk upload of all
  existing papers.
- Initial mirroring covers creation and transfer. Cross-system rename/move
  behavior is a later milestone. Deletion propagation remains off.
- Existing Acrobat/viewer annotations are preserved. For this user's future
  workflow, reMarkable supplies new annotation revisions.

## Confirmed configuration and sync scope

Read-only inspection found the sorter inbox at `Desktop\ToSort`, with `Topics`
as the sorter library root. Existing reMarkable routing maps `Literature` to
`Topics\Sorted`; automatic cloud checks are currently off. Paper Sorter's
background Watch & Launch setting is currently on.

The user confirmed tablet syncing stays beneath `Topics\Sorted`, linked to
`Literature`, while sorting remains available across `Topics`. Papers filed
elsewhere stay local unless a later explicit scope change is requested.

The user will provide representative pilot papers when implementation is ready
for live testing. Request them at that milestone; they are not required now.

Paths, account credentials, naming preferences, and linked roots belong in
per-user configuration. No personal paths are defaults for shared installations.
Migration must distinguish an existing enabled connection from the off default
for a fresh installation rather than silently enabling new cloud actions.

## reMarkable visibility and first-launch reconciliation

Settings contains a master reMarkable cloud-services toggle. When off, hide the
existing reMarkable tab and stop cloud operations. When on, reveal that tab and
its connection, routing, and review tools, adapting them for outgoing transfers
and reconciliation. Turning off retains saved links and previously downloaded
notes; it is distinct from disconnecting or forgetting credentials. Enabling
the integration alone does not authorize new upload or folder-write policies.

First-launch setup offers a review of PC/tablet mismatches within the selected
scope. Local discovery can run without connecting; tablet comparison requires
the user to enable and connect the integration. Show proposed links and repairs
before applying them, and make this review rerunnable after setup.

- Compare actual baseline PDF content where available to identify exact matches.
  Different annotation data must be retained even when the underlying paper is
  identical. Two separate tablet IDs remain distinct until explicitly linked.
- Use DOI, citation, title, and text similarity to suggest possible matches,
  never to silently merge revised papers or supplementary material.
- Flag papers present on only one side, differently named/missing folders,
  multiple copies, and different annotation versions. Discovery does not delete
  copies, move files, upload existing papers, or create folders automatically.
- Offer supported review actions such as linking an existing paper/folder,
  creating a missing counterpart, or explicitly transferring a selected paper.
  Different folder names can remain linked without forcing a rename.
- For papers annotated on both PC and tablet, retain the original and tablet
  annotations as separate sources under one confirmed paper identity. Combine
  their presentation only where provenance and deduplication are reliable;
  ambiguous note overlap, identity, and organization choices require review.
- Clearly distinguish actions the app can perform from cases needing a manual
  decision. Explain why an item was flagged and preserve work during repair.

## Storage and identity model

### Permanent source and reconstructable annotations

Keep one immutable baseline PDF for each actual source version. A legacy
baseline can already contain Acrobat annotations and must retain them exactly.
Record its content digest and preserve all tablet scene files, page ordering,
added/deleted-page information, and metadata needed for reconstruction.

When the cloud baseline is byte-identical to the local baseline, reference the
same stored content instead of permanently embedding another copy in a raw
archive. If they differ, retain both distinct source versions until their
relationship is resolved. A standalone `.rmdoc` export remains an explicit
portable backup operation and can contain the complete source.

Generate annotated PDFs for reading and the existing extraction pipeline. The
first working version can retain the latest generated copy. A later bounded
cache may evict only reproducible generated files after reconstruction and
source-link behavior have been tested. Offline pinning and user exports are
retained independently of disposable cache files.

Existing raw archives, PDFs, note histories, and source links must remain usable
through migration. No automatic cleanup is permitted merely because a new
storage layout exists. Cache/history retention policies must be explicit and
distinguish disposable data from saved research notes.

### One paper entry with source variants

Introduce stable paper identity independent of filename, folder path, DOI, or
tablet title. Track the baseline, cloud document ID, generated annotation view,
content digests, and originating annotation identities under that entry.

- A DOI or title alone is not proof of identity; supplementary information,
  revised manuscripts, and intentional copies must remain distinguishable.
- Namespaced annotation identities distinguish existing PDF annotations from
  tablet scene annotations. Reconstruction must not duplicate baseline notes.
- Annotation deletions and revisions apply within the owning source rather than
  removing notes from another source.
- Notebook links and full-page context need stable source resolution before
  generated PDFs can be evicted. Current exports point directly at PDF paths.
- Cloud-derived PDFs and generated files never enter the inbox or upload queue.

## Implementation stages and acceptance criteria

### 1. Source integration and optional features

Bring the sorter's reusable extraction, citation lookup, filename, and document
type modules into this project's package with explicit relative imports and
provenance. Retain the existing review-first behavior and optional Gemini and
local-only modes. Consolidate settings while keeping the Notes pipeline usable.

Acceptance: synthetic documents can be identified and named without launching
the old executable; unsupported files and incomplete metadata remain reviewable;
fresh libraries make no reMarkable requests; the source launcher works without
packaging tools. Copy only source resources needed at runtime.

### 2. Shared library identity and migration

Add the paper/source-variant model and durable operation records before uploads.
Provide a reversible database migration and a preview of existing record links.
Preserve configured watched projects and their notebook scope. A parent folder
and separately watched child cannot cause duplicate notes or unintended changes
to existing folder notebooks.

Acceptance: original and annotated variants present one intended paper entry;
legacy notes and annotation history survive; renames preserve identity; repeated
migration is safe; independent copies and source revisions are not silently
merged. First-launch review identifies exact matches, likely matches, one-sided
papers, folder mismatches, and independently annotated copies without changing
either library. Validate against a copied library before activating migration.

### 3. Combined inbox, filing, and annotation return

Add an Inbox review surface to the existing UI. Share validated settings and
background services, preserve filename editing and collision handling, and
index confirmed files in the intended note project. Downloaded annotation data
updates the associated paper instead of making a second visible entry.

Acceptance: incomplete downloads wait; cancel/skip keeps the inbox file;
collisions preserve existing files; returned annotations never re-enter sorting;
existing Notes search, previews, history, and notebook exports continue to work.

### 4. Queued PDF uploads

Implement cloud write support behind the explicit integration and send settings.
Resolve destinations through stable folder links. Persist the planned identity
before remote writes, verify completion, and reconcile ambiguous failures before
retrying so a timeout cannot create repeated tablet copies. Distinguish queued,
needs mapping, waiting for connection, and failed operations in the interface.

Acceptance: sorting succeeds offline; retries preserve one cloud document;
unsupported source types remain local; no bulk upload on first launch; existing
tablet PDFs can be linked without uploading them again. Protocol tests use fake
cloud clients before any live pilot.

### 5. Folder creation and storage limits

Add independent tablet-to-PC and PC-to-tablet creation controls under linked
roots. Use stable IDs and an operation journal to prevent loops and duplicate
folders. Existing names, case collisions, Windows-invalid names, and simultaneous
creation require review where identity cannot be established.

Add size accounting and bounded caches after source reconstruction and notebook
links are dependable. Avoid retaining the same baseline PDF in the archive,
blob cache, and local library permanently when content equality is established.

Acceptance: nested folder creation works both ways; unrelated roots are outside
scope; an empty counterpart stays empty; existing-paper transfer is an explicit
batch action; deleted/renamed folders are not silently recreated or propagated;
cache eviction preserves offline note access and user-owned exports.

### 6. Pilot and watcher transition

Offer one source launcher and one optional Watch & Launch helper. Keep the old
sorter installation available for rollback. Report existing watcher ownership
and perform the handover as an explicit migration step; development does not
rewrite Windows startup registrations.

Use a small pilot containing a clean PDF, an Acrobat-annotated PDF, and a paper
with tablet handwriting and highlights. Confirm naming, filing, upload placement,
legacy annotation appearance, returned notes, notebook scope, and offline
behavior before switching the normal workflow over.

## Information needed later

No credentials or additional files are required to begin. Later live validation
needs a selected pilot folder and representative papers, plus normal pairing if
the test account is not already connected. App naming, cache limits, and other
reversible presentation defaults can be decided during development.

## Progress

- [x] Inspect both source trees and current storage/transfer behavior.
- [x] Record agreed workflow, storage direction, and scope discrepancy.
- [x] Confirm Sorted-only tablet scope, first-launch mismatch review, and tab visibility.
- [x] Complete stage 1 source integration and offline checks.
- [x] Add review-first Inbox, safe filing/recovery, and PDF-only handoff.
- [x] Add additive paper identities, duplicate/folder review, and linked reader/export grouping.
- [x] Implement gated uploads and new-folder mirroring with synthetic cloud clients.
- [x] Add separate baseline/layer storage, offline reconstruction, and a bounded blob cache.
- [x] Audit tooltips and replace the key-removal checkbox with a staged Remove/Undo action.
- [ ] Complete stage 2 migration on a copied library.
- [ ] Add stable source resolution before any generated PDF cache eviction.
- [ ] Complete live pilot and source watcher transition.

The combined development version is implemented and tested with disposable
documents/libraries and fake cloud clients. Existing research PDFs, personal
configuration, account contents and Windows startup registrations have not been
changed during implementation. No updated executable was built.

Previous complete verification, before the staged key-removal change: all 489
discovered regression tests passed in the project virtual environment. Source
compilation and Git whitespace checks passed. The checks included a
locked-database startup, filing recovery, non-PDF exclusion, the previous
key-removal behavior, snapshotting settings when Save is clicked, and immediate
grouping of previously linked tablet variants.

Gemini now has a separate switch, off by default. Each user supplies their own
Windows-account-protected key. Ordinary sorter import excludes keys and leaves
Gemini and automatic inbox checking off. Remove saved key now marks a Settings
draft for deletion. Undo removal, Cancel, or closing Settings preserves the
stored key. Saving preferences commits deletion of this app's active saved key
and disables Gemini; a key must be entered again before using Gemini later.
Other key files/old sorter settings are not deleted.

Storage remains conservative: new tablet baselines share stored content and
layers are separate, but user-owned originals and legacy archives are retained.
A private baseline can still duplicate an original. Generated reading PDFs
remain retained because current Word links point directly to them. The 64 MB
default limit applies only to disposable cloud blobs, not the whole library.

Before normal use, validate a copied library and a small live pilot containing a
clean PDF, a legacy viewer-annotated PDF and a tablet-annotated example. The old
sorter remains available until that pilot and watcher handover are complete.
