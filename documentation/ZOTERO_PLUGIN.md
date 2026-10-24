# reMarkable Sync for Zotero

Formerly **Notable for Zotero**, this plugin's user interface lives inside Zotero. The installable XPI contains its
Windows processing helper and local OCR models. You do not install Python,
operate a terminal, or keep the original Notable application open.

This build targets **Zotero 10.0**, validated against 10.0.6 on Windows. The
installed application was verified as **Zotero 10.0.6** on October 20, 2026;
no application upgrade is needed. Development tests used disposable profiles
and did not install the plugin into the production library. This local preview
has no published automatic-update feed.

## Setup

1. In Zotero 10, open **Tools → Plugins**, choose **Install Plugin From File**
   from its gear menu, and select the complete reMarkable Sync XPI.
2. Open the **reMarkable tablet icon** from Zotero's top toolbar, or
   **reMarkable Sync for Zotero** from the Tools menu. This opens the plugin;
   Zotero's circular-arrow button syncs your Zotero account. Choose **Connect
   Zotero** and allow its normal local-library permission request.
3. Choose **Get reMarkable pairing code**, obtain the single-use code from your
   reMarkable account, and enter it in **Pair reMarkable**. Saved permissions and
   tablet credentials use Windows encryption tied to your account.
4. Refresh folders. Select a dedicated Zotero collection tree for tablet
   locations and the existing tablet folder tree to synchronize. Choose a
   default tablet destination for new papers. Zotero and tablet root names can
   differ. Subfolders inside these roots mirror each other.
5. Optionally choose a separate **ToSort** download folder. Do not use Zotero's
   data directory or its managed storage as this intake folder.
6. Leave local OCR enabled for scanned text and handwriting search. Expand
   **Naming templates** to customize each document type, or leave a template
   blank for Smart naming. **Save setup** saves these choices and leaves sync
   paused. Check the selected folders, then click **Sync now** when ready.

Keep ordinary research collections outside the dedicated tablet-location tree.
A paper can belong to any number of those research collections. Its selected
tablet destination determines its one tablet copy rather than creating copies
for each research category.

Destination menus show both sides of each connection: **Zotero: Windows imports
-- to organize → reMarkable: Literature**, for example. Both full paths also
appear on separate lines below the menu and update when you select another
destination. The folders can keep different names; no renaming is required.
Renaming a Zotero collection updates its displayed name and paths automatically,
including an open Review form. Its connection and saved filing choices keep
using the same collection; renaming does not move papers or start a sync.

## Bring in an existing Windows library

Use **Import library** for an existing collection of hundreds of papers. It is
separate from ToSort, which is for new arrivals.

1. Connect Zotero. Tablet pairing can wait. Choose a personal Zotero collection
   such as **Windows imports — to organize** and your existing literature folder.
2. Leave normal citation lookup enabled, or disable it for a local-only import.
   Supported DOI translators are preferred when the citation title agrees with
   the document text. Zotero's normal PDF recognition is the fallback and sends
   initial PDF text to Zotero's recognition service. No additional AI service is
   introduced. Existing curated references are retained on exact file reuse.
3. Choose **Scan folder — no library changes**. The recursive scan groups exact
   file copies, finds exact matches already stored in Zotero, and previews the
   exceptions. It does not reproduce old Windows categories as tablet folders.
4. Choose **Import / reuse … routine files** once for the routine batch. The
   original Windows files stay in place. Repeated scans reuse stored content;
   suspected versions, unreadable/password-protected files, ambiguous duplicates
   and unassigned supporting information are held for individual review.
5. After tablet Setup, run **Sync now**. In **Review**, choose a default tablet
   destination and **File … routine documents together**, then synchronize.
   A single byte-identical tablet match is linked in its existing mapped home.
   Unmatched papers use the chosen default destination. Several matches or a
   same-named tablet PDF with different bytes require individual review.

Missing author, year, journal, or DOI is not by itself an exception. Incomplete
citations retain usable filenames and can be corrected in Zotero before citing.
Scanned PDFs remain eligible; OCR is applied through the normal linked-PDF path.
The batch is revalidated against current files, references, and tablet matches.
An interrupted native import can finish its current file. A connection failure
pauses the saved batch; retry **Import / reuse … routine files** to resume, or
rescan to recover its stored copy without importing it again. Source files are never deleted by this
bulk importer. Resolving an exception uses Zotero's native reference/attachment
tools and the plugin's existing individual review controls, followed by a rescan.

For tag-based organization, a single tablet folder such as **Literature** is a
supported default destination. Research tags can overlap. Zotero collections also
overlap without duplicating references, so a few project collections are optional.
Existing tablet folders are not automatically flattened or converted to tags.

## Paper and page tags

- New imports and filing actions add reliable stated keywords as automatic
  whole-paper tags. Existing tags and their types are preserved. Normal sync
  does not repeatedly regenerate deleted keywords or invent topic tags.
- In **Review**, expand **Paper keywords and suggested tags**, then click
  **Find keywords and suggest tags**. Keywords show where they came from.
  Additional topic suggestions start unchecked. Select any you want, then
  choose **Use these tags when filing**. The paper is still awaiting its normal
  filing decision; checking suggestions does not import or approve it.
- For a PDF already stored in Zotero, open **Tags → Find keywords and suggest
  paper tags**, search its title, and choose the intended PDF. **Add keywords
  and selected tags** changes only that paper. Existing papers are not mass
  retagged when the update is installed.
- Suggestions use local English text statistics and your existing tag
  vocabulary. They can include imperfect phrases, so review them. No document
  text is sent to a new service, and no additional model is downloaded. Scanned
  papers without readable text keep their existing tags; add tags manually.
- Whole-paper tags synchronize both ways, including publisher keywords imported
  automatically by Zotero. First synchronization combines existing labels.
  Subsequent additions, renames, and removals propagate in either direction.
  Existing Zotero automatic/manual tag types are retained for unchanged labels.
- Open a linked PDF in Zotero and click **Tag this page** in its reader toolbar.
  Add or remove **Paper tags** and **Page tags**, then click **Save tags**. These
  are separate scopes with the same reusable vocabulary. They reach the tablet
  on the next sync; page tags never become whole-paper tags automatically.
- Open **reMarkable Sync → Tags** to search either scope or both. **Open page** jumps to
  the matching page. Paper tags also remain searchable through Zotero's normal
  tag selector. Plugin page tags use private metadata and this page-search view;
  they are not native Zotero annotation tags or Advanced Search conditions.
- Page identity uses the tablet's stable page UUID. Inserting, deleting or
  rearranging pages does not reassign a tag to a different page. A stale PDF or
  unknown/deleted target page requires review. Editing ordinary highlight or
  comment tags in Zotero does not create tablet page tags.
- A tag-only sync preserves the PDF and pen-layer bytes, without rendering or
  OCR again. A link with an unsupported annotation format still waits for review.
- Interrupted tag writes are journaled. Retry **Sync now**. If both copies were
  edited during an ambiguous interruption, the page editor offers **Combine
  current tags and retry**; this deliberately retains labels present on either
  copy. Earlier plugin page tags already promoted into paper tags are flagged
  rather than silently removed or copied back to the tablet.

## Everyday use

- Download to ToSort, use the Zotero Connector, import into Zotero, or add a PDF
  on your tablet. New documents enter **Review** before filing or transfer.
- Routine documents can be filed together from **Review**. Individual review is
  for material exceptions, not a requirement to perfect every citation. Review
  the title, document type, filename preview, research collections, and tablet
  destination when an exception needs attention. **Approve & file** applies that decision. Existing Zotero
  citation fields, dissertation information, and SI attachments stay in Zotero.
- For a supplement, choose **Supporting Information**, click **Find main paper**,
  and select its main article in Zotero. Filing attaches the supplement beneath
  that article and keeps the article's title and citation unchanged. If the
  main article is not in Zotero yet, import it first, then find it again here.
- Keep reviewing while a batch runs. Review fields remain editable, and
  **Add to filing queue** saves your choices for the next paper. Filings run
  one at a time. A queued approval can be removed before it starts. File and
  citation changes are checked again when its turn comes; a problem pauses
  the queue with an explanation. Stop pauses the queue too. Queued choices
  survive closing Zotero and wait for **Resume queued filings** after reopening.
  Filing saves the decision; it does not start a whole-library sync. Use
  **Sync now** to transfer approved PDFs and tablet notes. A filing submitted
  during a sync asks that sync to yield at its next safe boundary.
- If identical PC/tablet originals exist, review offers an explicit link. A
  matching title or DOI alone does not authorize applying ink to another file.
  Different PDF bytes currently stay separate until their editions are checked.
- New tablet annotations update the current local PDF automatically. Ink stays
  in the PDF; supported highlights/comments also enter Zotero's native reader.
  The clean baseline, raw tablet sources, and prior rendered versions are kept
  privately for recovery.
- Use Zotero's **Everything** quick search or **Attachment Content** conditions
  in Advanced Search. Indexing covers every page, extracted quotations,
  comments, printed OCR, and machine-read handwriting. Handwriting recognition
  can misread scientific notation; the original marks remain authoritative.
- **Linked papers** provides native-library navigation, rename/move controls,
  unlink/resume, search-index rebuilding, and link history. Unlink keeps both
  copies. Research-collection membership changes are distinct from deletion.
- **Open paper** in an individual review opens the saved file in your usual
  reader without approving or importing it. **Browse all papers** also lets you
  inspect documents in the routine batch. For a new tablet paper, this opens the
  downloaded original; handwriting is added when its approved copy syncs.
- The toolbar badge indicates pending reviews or connection problems. Sync
  runs while Zotero is open and this workspace is closed, with retry backoff.
  Opening the workspace stops an automatic check at its next cancellation
  point without changing your saved automatic-sync preference. Manual **Sync
  now** works while the workspace is open. Automatic checks normally wait five
  minutes between runs, with a longer delay after errors.
- A blue activity panel shows the current job, file count when available, and
  elapsed time. It also reports how long it has been since the last progress
  update. Review navigation and **Open paper** stay available during a job;
  actions that change files wait for the current job to finish. **Stop** stops
  the current operation; the same button says **Pause sync** when idle.
- **Pause sync** stops the current
  operation and keeps syncing paused across restarts. **Sync now** starts the
  saved connection again. Automatic sync starts after that only when enabled
  in Setup. Saving setup always pauses first; it never starts a transfer.

## Change or disconnect a folder

1. Open **Setup → Change folder**. Sync pauses before any selections change.
2. Choose the Zotero collection, the new reMarkable folder, and a default
   destination inside that folder. Click **Review folder change**.
3. Check the two paths and the included subfolders. Expand the lists to see old
   folders that will stay outside the new sync. Click **Save folder change**.
4. Papers, handwritten notes, tags, and collections stay in place. Automatic sync
   is off. Click **Sync now** when you are ready to use the new selection.

Old paper links, page tags, review decisions, and recovery sources stay with
their previous connection. Previously mirrored subfolders and linked papers
are kept out of the new connection, including later children of those folders.
New folders included in the preview mirror on the first sync. Changing the
connection does not move existing tablet papers into a different folder.

To resume a previous connection, choose its same Zotero and reMarkable folders
again. The preview reports how many previous links will be restored. **Previous
folder connections** in Setup lists the retained connections. Their private
page-tag search state becomes active again when that connection is restored.

**Disconnect folder → Confirm disconnect** stops using the selected folder
while preserving both libraries and the pairing credentials. It works offline.
Cancel leaves the current connection selected and paused. No folder, paper or
annotation is deleted by changing or disconnecting a connection.

## Deletion decisions

A confirmed tablet trash operation produces a pending notification:

| Choice | Result |
| --- | --- |
| Restore on tablet | Restores the recorded tablet copy to its mapped home. |
| Delete PDF only | Sends the matching Zotero PDF to Trash; preserves the reference, notes, and other SI attachments. A separate matching source/view pair is handled together. |
| Delete everything | Sends the whole Zotero reference, including its attached notes and SI, to native Trash. |

Closing the window leaves the decision pending. Missing items and offline
connections are not proof of deletion. The reference inventory is rechecked
before a native trash action; intervening note/PDF changes require review.
No operation permanently empties Zotero or tablet Trash.

Trashing a linked reference in Zotero instead offers **Keep tablet copy** or
**Trash tablet copy**. Its link pauses so it cannot be recreated accidentally.

## Boundaries

- Independent desktop annotations are preserved. If they would be overwritten
  by a tablet refresh, that link stops for review. Initial adoption can keep a
  separate desktop-notes attachment when necessary. Reverse annotation transfer
  to the tablet is deferred.
- Word and modern PowerPoint files can be named and stored in Zotero. They
  require a PDF version for tablet reading; this build does not claim automatic
  Office-to-PDF conversion or specialized old-PowerPoint processing.
- Native tablet notebooks and EPUB annotation transfer, Word notebook exports,
  hosted AI naming and a custom Scopus parser are
  outside the agreed initial scope. Native Zotero SI organization stays intact.
- Page tags use this computer's plugin state and the reMarkable cloud. Zotero's
  own account sync does not independently transport that private page-tag state;
  another configured plugin installation must retrieve it from reMarkable.
- Unsupported page layouts or annotation formats stop that conversion and
  retain the sources. Margin expansion supports ordinary uncropped, unrotated
  pages; expanded ink on rotated/cropped pages requires further validation.
- Deleting/moving a mapped folder outside the selected roots stops its mapping
  for review. It is never treated as permission to erase its papers or recreate
  a deleted folder. Use **Change folder** to choose another scope; it preserves
  the previous connection instead of moving or deleting its documents.

## Updating the plugin

Version **0.7.0** refreshes matches against the current Zotero library, keeps
existing tablet folders during batch filing, avoids numbered download names,
and preserves curated reference titles when linking. Older unlinked approvals
with newly found duplicates or numbered filenames return to Review before
transfer. Existing references are retained for recovery. Filing no longer
launches a full sync; queues recover unfinished work and live connection counts
distinguish saved approvals, connected papers, and received PDFs. Independent
paper failures are reported while the rest of a sync continues.

Version **0.6.0** shows both the Zotero collection and reMarkable folder in
destination menus for batch filing, individual review, and moving linked
papers. The selected pair is repeated on two readable lines below each menu.
It also adds Supporting Information with an explicit main-paper selector and
a saved filing queue so review can continue while another batch is running.

Version **0.5.0** adds stated paper keywords, reviewable topic-tag suggestions,
an independently scrolling review list, and the rectangle-with-R toolbar icon.
The paper list matches the right review panel's height on wide windows; narrow
windows use a bounded list above the form. Selection and list position remain
available while browsing. The 0.5.0 source and component notices accompany its XPI.

Version **0.4.2** keeps automatic checks out of the open workspace, reuses
unchanged pending-paper information, adds a visible activity panel, and lets
you open papers from Review. Plugin copy and this guide use Oxford commas.

Version **0.4.1** fixes a Windows pipe-encoding crash when titles or tags contain
characters outside the system code page. Saved review queues remain intact.
New tablet papers now say **Checking new tablet paper** while being checked;
that progress does not mean they have already been imported. The status directs
you to **Review** when documents need filing. This was verified against a copy
of the affected 140-document queue and the packaged helper.

Version **0.4.0** adds Change folder, Disconnect folder, and persistent Pause sync,
separates saving setup from starting sync, and gives the Zotero toolbar entry a
distinct tablet icon. Existing sync records stay in their original location;
later connections get their own private state directories. Install the new
XPI over the existing plugin using **Tools → Plugins → Install Plugin From File**.
The internal extension ID stays the same, so this is an update of the existing
plugin. Re-pairing and re-importing papers should not be necessary.

Wait for the current sync/import to finish before updating. The plugin may
close its workspace and briefly stop its helper during replacement. Existing
Zotero references, attachments, collections, and tablet documents remain in their
current locations. The profile's `notable` folder, including its `connections`
subfolder and `config.json`, keeps pairing credentials,
configuration, document links, page tags, pending decisions, and recovery files.
Keep that folder when backing up or moving the installation; Zotero account
sync alone is not a backup of this private state.

Future updates that change sync behavior or stored formats require separate
migration and recovery validation. After changing connections in 0.4.0, keep
using 0.4.0 or later; older builds do not understand the saved connection
selection. This preview still has no published automatic-update feed.

See [component notices](ZOTERO_PLUGIN_NOTICES.md),
[keyword implementation and validation](research/2026-10-23-paper-keywords.md), and the
[folder-connection implementation/reuse record](research/2026-10-22-folder-connections.md) for
technical and validation details. Developer test tools remain separate from the
user workflow.
