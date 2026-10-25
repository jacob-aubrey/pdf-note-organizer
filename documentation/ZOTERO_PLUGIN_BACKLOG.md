# Plugin follow-up status

## Import progress counts the selected routine batch — fixed October 24, 2026

Recorded October 23, 2026. The user explicitly deferred this as nonurgent.

The Import / reuse button correctly counts only eligible, unfinished routine
files. The active progress message instead uses positions and the total from
the full scanned plan. For example, a 489-file routine batch displays a total
of 573, including 84 held-back cases. The importer skips those cases; the
display does not represent additional import authorization.

The scheduled repair now counts only eligible, unfinished work in the active
invocation, including resumed batches. Held cases remain separate. Mixed
routine/exception/completed plans have targeted regression coverage; see
`SCHEDULED_REPAIR_2026-10-24.md` for the session results and remaining limits.
