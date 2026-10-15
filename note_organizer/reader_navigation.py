"""Occurrence navigation in the currently displayed research result order."""
from dataclasses import dataclass


@dataclass(frozen=True)
class NavigationTarget:
    row: str
    entry_index: int
    hit_index: int | None
    hit: dict | None
    ordinal: int
    total: int


def entry_hits(entry):
    """Return backend occurrences; browse and NOT-only rows have none."""
    return tuple(entry.get("search_hits") or ())


def _rows(entries, row_ids):
    """Read visual order without allocating an object per occurrence.

    Numeric tree row IDs refer to the entry array; sorting the tree must never
    change that mapping. Stale rows during an asynchronous refresh are skipped.
    """
    result, seen = [], set()
    for raw_row in row_ids:
        row = str(raw_row)
        if row in seen:
            continue
        seen.add(row)
        try:
            index = int(row)
        except (ValueError, TypeError):
            continue
        if not 0 <= index < len(entries):
            continue
        hits = entries[index].get("search_hits") or ()
        result.append((row, index, hits))
    return result


def match_locations(entries, row_ids):
    """Flatten visual order, retaining one stop for every visible result."""
    result = []
    for row, index, hits in _rows(entries, row_ids):
        result.extend((row, index, hit_index, hit) for hit_index, hit in enumerate(hits))
        if not hits:
            result.append((row, index, None, None))
    total = len(result)
    return tuple(NavigationTarget(row, index, hit_index, hit, ordinal, total)
                 for ordinal, (row, index, hit_index, hit) in enumerate(result, 1))


def _selected_index(rows, selected_row, hit_index):
    row = str(selected_row) if selected_row is not None else None
    offset = 0
    for row_id, _, hits in rows:
        if row_id == row:
            local = hit_index if isinstance(hit_index, int) and 0 <= hit_index < len(hits) else 0
            return offset + local
        offset += max(1, len(hits))
    return None


def _target_at(rows, index, total):
    offset = 0
    for row, entry_index, hits in rows:
        count = max(1, len(hits))
        if offset <= index < offset + count:
            hit_index = index - offset if hits else None
            hit = hits[hit_index] if hits else None
            return NavigationTarget(row, entry_index, hit_index, hit, index + 1, total)
        offset += count
    return None


def current_target(entries, row_ids, selected_row=None, hit_index=None):
    """Return the selected occurrence for a counter without moving anything."""
    rows = _rows(entries, row_ids)
    if not rows:
        return None
    index = _selected_index(rows, selected_row, hit_index)
    return _target_at(rows, index, sum(max(1, len(hits)) for _, _, hits in rows)) if index is not None else None


def navigation_target(entries, row_ids, selected_row=None, hit_index=None, step=1):
    """Move across individual hits, then results, wrapping at either end.

    Without a selected result, Next chooses the first stop and Previous the
    last. A result whose old occurrence has disappeared starts at its first
    remaining occurrence before applying the step.
    """
    rows = _rows(entries, row_ids)
    if not rows:
        return None
    total = sum(max(1, len(hits)) for _, _, hits in rows)
    index = _selected_index(rows, selected_row, hit_index)
    if index is None:
        index = 0 if step >= 0 else total - 1
    else:
        index = (index + step) % total
    return _target_at(rows, index, total)
