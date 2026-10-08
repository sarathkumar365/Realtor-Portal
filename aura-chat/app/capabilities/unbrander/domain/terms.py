"""How a hit-list term is found in text. One definition, used by the tools that
remove a term and by verify() that checks it is gone: if the two matched
differently, verify would pass what the tools never looked for."""

import re

SHORT = 3  # below this a term matches only as a whole, case-sensitive word


# Contact details a buyer must not see, found by code in the text of the pages
# that stay, as the skill's own hit list did. URLs and domains are not here:
# brochures quote legitimate ones (an ENERGY STAR page on canada.ca).
PHONE = re.compile(r"\(?\b\d{3}\)?[\s.-]?\d{3}[\s.-]\d{4}\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def term_pattern(term: str, *, anchored: bool = True) -> re.Pattern:
    """Tolerates one separator between any two characters, so "SouthCal" also
    finds "South Cal", "South-Cal" and letter-spaced "S O U T H C A L", and an
    email or a phone number matches with its own punctuation. Any one character
    that is not a letter or digit separates: a narrower set never matched
    "sales@remingtonbrightside.ca" (the "@")."""
    if len(term) < SHORT:
        return re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])")
    chars = [re.escape(char) for char in term if char.isalnum()]
    body = r"[^A-Za-z0-9]?".join(chars)
    if anchored:
        body = rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])"
    return re.compile(body, re.IGNORECASE)
