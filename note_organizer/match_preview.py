"""Compact PDF excerpts with positions for highlighting individual occurrences."""
from bisect import bisect_left


def excerpt_display(context, excerpt, hits):
    start, end = excerpt["start"], excerpt["end"]
    chars, offsets = [], []
    for index, char in enumerate(context[start:end], start):
        if char.isspace():
            if not chars or chars[-1] == " ":
                continue
            char = " "
        chars.append(char)
        offsets.append(index)
    if chars and chars[-1] == " ":
        chars.pop()
        offsets.pop()
    prefix = "…" if start else ""
    text = prefix + "".join(chars) + ("…" if end < len(context) else "")
    ranges = {}
    for hit_index in excerpt["hit_indices"]:
        hit = hits[hit_index]
        left = len(prefix) + bisect_left(offsets, hit["start"])
        right = len(prefix) + bisect_left(offsets, min(hit["end"], end))
        if right > left:
            ranges[hit_index] = (left, right)
    return text, ranges
