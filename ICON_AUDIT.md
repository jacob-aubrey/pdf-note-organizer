# Whole-app icon audit

October 8 follow-up: path controls consistently use a small copy icon with
the action label and dynamic tooltip **Copy full path**. **Copy details** shows
its icon and text because it copies the full explanation rather than a single
location. Notes and library review share the plain magnifying-glass Search
label. The final full suite passed all 649 tests, including icon and layout
checks. No executable was built.

October 7, 2026. Reviewed button and action-menu icons across Inbox, Library,
Notes, reMarkable, Settings, review windows, and dialogs. Tabs and status text
keep their existing presentation. All other icons remain unchanged.

| Action | Previous icon | Current icon |
| --- | --- | --- |
| Review library… / Check library | `scan` | `folder-search` (user's choice) |
| Link selected copies… | `unlink` | `link` |
| Add documents… | `folder-plus` | `files` |
| Review selected | `file-text` | `file-search` |
| Send selected PDF… | `folder-sync` | `file-up` |
| Transfer queue… | `list-filter` | `list-todo` |
| Skip | `x` | `skip-forward` |
| Remove saved key | `unlink` | `trash-2` |
| Fit width | `maximize` | `move-horizontal` |
| Undo removal | `rotate-ccw` | `rotate-ccw` |

Review folder is now labeled **Open review folder** to make clear that it opens
a directory. The active **Search in… •** label is normalized for icon lookup to
prevent a `KeyError`; its displayed label, active indicator, and tooltip remain.
The transfer-list refresh timer is now owned by the main window, so closing
the list does not leave an invalid Tcl callback.

Icons remain locally bundled Lucide assets. Additions use the existing pinned
revision `f12b0de177fbc2a6795e99be065887e72b237123`; source attribution and
licensing are unchanged. See `note_organizer/assets/icons/SOURCE.txt` and
`LICENSE.txt`. No executable was built for these changes.

Verification: 76 combined-workflow, Settings, tooltip, and Inbox tests passed
after the staged key-removal update; all 19 UI-polish tests passed after the
icon and timer fixes. These include applying/resetting search filters and
rendering actions in review and transfer windows. All 41 mapped icons have
readable SVG and PNG assets. New icons were visually checked at 72px and 16px
in normal and disabled states. Source compilation and whitespace checks passed.
