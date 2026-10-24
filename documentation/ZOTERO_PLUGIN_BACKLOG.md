# Deferred plugin updates

## Import progress should count the selected routine batch

Recorded October 23, 2026. The user explicitly deferred this as nonurgent.

The Import / reuse button correctly counts only eligible, unfinished routine
files. The active progress message instead uses positions and the total from
the full scanned plan. For example, a 489-file routine batch displays a total
of 573, including 84 held-back cases. The importer skips those cases; the
display does not represent additional import authorization.

Later, make the current position and total reflect the eligible work in that
invocation, including resumed batches. Keep skipped cases separate, preserve
all existing checks, and test mixed routine/exception/completed plans.
