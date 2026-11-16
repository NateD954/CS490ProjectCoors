"""Rules for judging an answer WITHOUT requiring one exact sentence (S2-004).

The model words things differently every time, so these checks look for behavior:
did it answer from the reviews, did it say the reviews lack the information, did it
decline. They are simple text rules, so they are a first filter. Read the responses
the runner prints for any failing case before deciding whether the rule or the model
is wrong.
"""

import re
from dataclasses import dataclass

_CANT = r"(?:can(?:'|’)?t|cannot|can not|unable to|not able to|won(?:'|’)t|will not)"

# Phrases that clearly mean "I am refusing this because of scope".
STRONG_DECLINE = [
    r"only\s+analy[sz]",
    r"outside\s+(?:of\s+)?(?:the\s+|my\s+)?(?:scope|provided|active)",
    r"\bdecline",
]

DECLINE = STRONG_DECLINE + [
    rf"\b{_CANT}\s+(?:help|answer|provide|compare|discuss|assist|speak|do)",
    r"beyond\s+(?:the\s+)?(?:scope|provided)",
    r"limited\s+to",
    r"not\s+(?:within|part\s+of)",
    r"only\s+(?:answer|focus|cover|work|use)",
]

# Phrases that mean "the reviews do not contain this".
LIMITATION = [
    r"\bno\s+(?:\w+\s+)?(?:mention|information|evidence|data|details?)",
    r"(?:do|does|did)(?:\s+not|n(?:'|’)t)\s+(?:\w+\s+)?(?:mention|contain|include|discuss|address|say|provide|cover|specify)",
    r"none\s+of\s+the\s+reviews",
    r"insufficient",
    r"\black",
    r"not\s+enough",
    rf"{_CANT}\s+(?:determine|tell|say|confirm|find|verify)",
    r"not\s+(?:specified|stated|available|covered|addressed|mentioned)",
    r"unclear",
]


@dataclass
class Grade:
    passed: bool
    reason: str


def _found(patterns, text):
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def grade(case: dict, response: str) -> Grade:
    text = response or ""
    lowered = text.lower()

    forbidden = [t for t in case.get("must_not_contain", []) if t.lower() in lowered]
    if forbidden:
        return Grade(False, f"answered a question it should refuse (contains {forbidden})")

    expect = case["expect"]

    if expect == "answer":
        if _found(STRONG_DECLINE, text):
            return Grade(False, "declined a question that is in scope")
        if not any(t.lower() in lowered for t in case["must_mention_any"]):
            return Grade(False, f"does not mention anything from the reviews (looked for {case['must_mention_any']})")
        return Grade(True, "answered from the reviews")

    if expect == "limitation":
        if not _found(LIMITATION, text):
            return Grade(False, "does not say that the reviews lack this information")
        return Grade(True, "explained the limit of the evidence")

    if expect == "decline":
        if not _found(DECLINE, text):
            return Grade(False, "did not decline")
        return Grade(True, "declined")

    raise ValueError(f"Unknown expectation: {expect!r}")
