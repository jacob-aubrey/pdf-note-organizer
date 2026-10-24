# Folder connections and toolbar clarity: 0.4.0

## Reuse decision

This release retains the existing Zotero native-library client, reMarkable
transport, sync engine, SQLite state and atomic configuration writer. A small
connection manager isolates their existing state; replacing the engine would
also replace recovery, page-tag and review behavior that this workflow needs.
No new dependency or recurring setup is introduced.

Before implementation, the upstream
[zotero-remarkable-sync](https://github.com/bpiwowar/zotero-remarkable-sync)
project and its actual v0.2.1 manifest/README were checked. Its latest release
was v0.2.1 on October 22, 2026, and the repository was active and not archived.
The README specifies AGPL-3.0-or-later. Its
[versioned manifest](https://github.com/bpiwowar/zotero-remarkable-sync/blob/v0.2.1/addon/manifest.json)
declares Zotero 6.999 through 10.*. This updates the earlier compatibility
survey; Zotero 10 is now declared supported. The README describes tag-based
selection, scheduled/on-demand transfer, rmapi-js and experimental .rm v6
handling. It does not document an adapter for our collection-root connections,
retained review decisions, page tags and recovery history. Windows behavior
was not independently validated for that candidate. No upstream code was copied.

The existing standard-library SQLite access and atomic file writer suffice for
local state selection. Relevant upstream references are the
[Zotero 10 developer documentation](https://www.zotero.org/support/dev/zotero_10_for_developers)
and [Python SQLite documentation](https://docs.python.org/3/library/sqlite3.html).
The toolbar reuses Lucide's tablet SVG from the already pinned revision
`f12b0de177fbc2a6795e99be065887e72b237123`, under the bundled ISC/Feather MIT
notices. Native Gecko folder menus and the existing shared button styling remain
in use. The tested runtime is Windows x64 Zotero 10.0.6; cross-platform results
are not claimed.

## Behavior and persistence

- Save setup saves settings and pauses transfers. Sync now is the explicit
  transfer action. Pause sync interrupts current work and persists across restart.
- Change folder pauses first, reads metadata, previews full paths and included
  or excluded subfolders, then requires a revalidated confirmation to save.
  Disconnect folder has a separate confirmation and works offline.
- Neither operation moves or deletes library documents, notes or collections.
  Pairing credentials remain available. Automatic sync is off for a changed
  connection until the user chooses their settings and resumes it.
- Legacy state remains in `notable/bridge`, `review` and `incoming`. New state
  uses `notable/connections/<connection-id>/`. An atomic `config.json` update is
  the commit point; preparation failures leave the existing selection intact.
- Old links, source files, page tags, pending decisions and journals remain with
  the previous connection. Selecting the same server and both root IDs restores
  that connection. Old linked documents and mapped subtrees, including newly
  created descendants, are excluded from a different connection. A missing
  archived bridge database blocks transfers instead of forgetting exclusions.
- Confirmation tokens include current configuration, bridge/review state and
  relevant metadata. Intervening changes require another preview.
- The main Zotero toolbar entry uses a tablet icon, the label reMarkable and
  an Open reMarkable Sync tooltip. It opens the workspace. Zotero's own account
  sync control is unchanged. The Tags controls retain actual tag-shaped icons.

The extension ID remains `notable-companion@local.invalid`. Backups must include
the complete `notable` profile directory. After switching connections, use 0.4.0
or later because earlier releases do not understand the connection pointer.
There is still no published automatic-update feed.

## Validation

The related unit suite passed 87 tests, including 19 connection tests. Coverage
includes legacy state, blank bindings, atomic-save failure/retry, stale previews,
offline disconnect, preserved credentials, restart/restoration, exclusions,
disabled automatic requests and local indexing while transfers are paused.

The packaged helper and actual Zotero 10.0.6 in a disposable Windows profile
passed 11 workflow checks. These verify native catalog and attachment-byte
preservation, isolation of old mirrored folders, restored links/page tags,
disconnect, actual button gestures, tablet launcher, printed OCR and native
comment search. Cloud documents are in-memory fixtures; no real account or
tablet was accessed. Button gesture checks mock RPC only for the gesture test;
separate backend/native checks exercise the real handlers and native library.

The populated UI matrix covers five tabs in light/dark at 1040px and dark at
640px, six folder-change/disconnect confirmation views and three actual native
menu interactions. Geometry checks detect intersecting buttons, horizontal
overflow and escaped native options. Screenshots are inspected separately.

Evidence is local under `.test-tmp/zotero-folder-04-native-03`,
`.test-tmp/zotero-folder-04-unit-results.json` and
`.test-tmp/zotero-plugin-04-build-ocr.log`. Earlier failing fixtures are retained
as diagnostic history; they are not counted as passing acceptance runs. Native
testing found and corrected a cancellation flag that had blocked local OCR
after disconnect. This release was built and tested without installing it into
the production Zotero profile or changing the user's Literature connection.
