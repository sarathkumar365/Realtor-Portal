"""How a hit-list term is found in text. One definition, used by the tools that
remove a term and by verify() that checks it is gone: if the two matched
differently, verify would pass what the tools never looked for."""

import re

SHORT = 3  # below this a term matches only as a whole, case-sensitive word


def term_pattern(term: str, *, anchored: bool = True) -> re.Pattern:
    """Tolerates one separator between any two characters, so "SouthCal" also
    finds "South Cal", "South-Cal" and letter-spaced "S O U T H C A L"."""
    if len(term) < SHORT:
        return re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])")
    chars = [re.escape(c) for c in term if c.isalnum()]
    body = r"[\s\-_.·]?".join(chars)
    if anchored:
        body = rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])"
    return re.compile(body, re.IGNORECASE)
