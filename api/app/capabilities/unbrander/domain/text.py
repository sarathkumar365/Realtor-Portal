"""Words and boxes: the small helpers the tools, verify() and the editor share, so
the three never disagree on how a match maps back to words or what an area is."""

from collections import Counter
from collections.abc import Callable

from .pdf import BBox, Word


def joined(words: list[Word]) -> tuple[str, list[int]]:
    """The words joined by spaces, and where each word starts, so a match that
    spans words ("Arista Homes", "S O U T H") maps back to their boxes."""
    starts, position = [], 0
    for word in words:
        starts.append(position)
        position += len(word.text) + 1
    return " ".join(word.text for word in words), starts


def words_in_span(starts: list[int], words: list[Word], start: int, end: int) -> set[int]:
    """The indexes of the words a match from `start` to `end` touches."""
    return {i for i, word_start in enumerate(starts)
            if word_start < end and word_start + len(words[i].text) > start}


def missing(before: list[Word], after: list[Word],
            key: Callable[[str], str] = str) -> list[Word]:
    """The words of `before` that `after` no longer has, counted, so a page with
    three "BATH" labels that lost one reports one. Compared by `key` of the text,
    never by box: rewriting a page moves unchanged words by about 1e-4 points."""
    left = Counter(key(word.text) for word in after)
    out = []
    for word in before:
        found = key(word.text)
        if left[found]:
            left[found] -= 1
        else:
            out.append(word)
    return out


def intersects(first: BBox, second: BBox) -> bool:
    """True when the boxes share any interior, even when one has no area: a
    zero-width word inside a box still counts as held by it."""
    return (first[0] < second[2] and second[0] < first[2]
            and first[1] < second[3] and second[1] < first[3])


def area(bbox: BBox) -> float:
    return max(bbox[2] - bbox[0], 0) * max(bbox[3] - bbox[1], 0)


def overlap(first: BBox, second: BBox) -> float:
    return area((max(first[0], second[0]), max(first[1], second[1]),
                 min(first[2], second[2]), min(first[3], second[3])))


def union(boxes: list[BBox]) -> BBox:
    return (min(box[0] for box in boxes), min(box[1] for box in boxes),
            max(box[2] for box in boxes), max(box[3] for box in boxes))
