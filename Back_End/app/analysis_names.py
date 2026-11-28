"""Rules for the name a user gives an analysis (S3-001, reused by rename in S3-002).

The name is only a label for the user. It is stored separately from the source URL and
changing it never touches the reviews, the source or the Q&A history.
"""
import re

MAX_NAME_LENGTH = 120  # keep in step with MAX_NAME_LENGTH in the frontend's lib/config.ts


def cleanName(raw) -> tuple[str, str | None]:
    """Return (cleaned name, problem). problem is None when the name is usable.

    Cleaning trims the ends and turns any run of spaces, tabs or line breaks into one space.
    A name is unusable if it is empty, too long, contains control characters, or has no
    letter or number in it (for example "---" or "???").
    """
    text = raw if isinstance(raw, str) else ""
    if any(ord(c) < 32 and c not in "\t\n\r" or ord(c) == 127 for c in text):
        return "", "The name contains characters that can't be used."
    name = re.sub(r"\s+", " ", text).strip()
    if not name:
        return name, "Enter a name for this analysis."
    if len(name) > MAX_NAME_LENGTH:
        return name, f"Keep the name under {MAX_NAME_LENGTH} characters."
    if not any(c.isalnum() for c in name):
        return name, "Use at least one letter or number in the name."
    return name, None
