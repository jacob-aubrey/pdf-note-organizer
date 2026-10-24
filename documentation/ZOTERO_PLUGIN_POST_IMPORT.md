# Authorized update after the active Windows import

Completed and packaged as **0.5.0** on October 23, 2026. The watched import
finished with 486 completed records and 87 held for review. The new release has
not been installed into the production profile, and live tags were not changed.

The user authorized these changes on October 23, 2026. Wait for the current
Windows-to-Zotero import to finish before implementing and packaging them.
The heartbeat `finish-zotero-import-then-add-paper-tags` monitors that import.
Do not change the running installation or interrupt the import.

## Paper keywords and suggested tags

Retain existing citation-supplied tags. Add a paper's explicitly stated keywords
when reliably identified. Offer additional topic tags for the user to accept or
reject before adding them. Reuse the existing vocabulary, distinguish keywords
from suggestions, and preserve existing tag types, page tags, and handwriting.
Do not introduce a new hosted AI service or silently apply suggested topics.

## Scrollable paper list in Review

Make the left paper list scroll independently, with its height matching the
rendered document-details panel on the right. A long list must not stretch the
page. Preserve the selected paper and list position when switching papers.
Support keyboard navigation, mouse-wheel scrolling, resizing, changes in the
right panel's height, and the narrow-window layout.

## Tablet toolbar icon

Replace the current tablet icon's bottom dot with a clear capital R inside a
simple rectangle. The user proposed the reMarkable symbol, rM, or R; the selected
recommendation is R for clarity at toolbar size. Keep the accessible name and
Open reMarkable Sync tooltip. Use a small code-native SVG with the current icon
styling; inspect it at actual toolbar size in light and dark themes. No new
bitmap generator, external font, or icon dependency is needed.

## Delivery and deferred work

Use Oxford commas throughout plugin copy. Follow AGENTS.md, test with disposable
profiles and synthetic data, and provide a tested XPI. Production installation
and retroactive live-library tag changes are not authorized by this update.
The import progress-counter mismatch remains explicitly deferred in
ZOTERO_PLUGIN_BACKLOG.md.
