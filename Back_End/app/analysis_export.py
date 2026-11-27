"""Builds the Markdown export of a saved analysis (S3-018).

Everything here is a plain function with no database access, so it is easy to test.
The route in main.py gathers the data and calls buildAnalysisMarkdown.
"""

import re
import unicodedata
from datetime import datetime, timezone

PLATFORM_LABELS = {"GOOGLE_MAPS": "Google Maps"}
STATUS_LABELS = {
    "not_started": "Not started",
    "in_progress": "In progress",
    "completed": "Completed",
    "partial": "Completed with skips",
    "failed": "Failed",
}
NOT_RECORDED = "Not recorded"
# The history keeps only the question, the answer and the time. It does not record which
# reviews backed an answer, so none are listed (nothing is invented to fill the gap).
EVIDENCE_NOTE = "_The specific reviews behind each answer are not stored with the history, so no per-answer evidence is listed._"

_SPECIAL = re.compile(r"([\\`*_\[\]<>#|])")


def inlineText(value) -> str:
    """One line of text with Markdown characters escaped, for names and short fields."""
    text = " ".join(str(value if value is not None else "").split())
    return _SPECIAL.sub(r"\\\1", text)


def quoteBlock(value) -> str:
    """Text as a block quote. Every line starts with '>', so it cannot become a heading or list."""
    text = str(value if value is not None else "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = text.strip().replace("<", "\\<")
    return "\n".join(f"> {line}" if line.strip() else ">" for line in text.split("\n"))


def _parse(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def formatDay(value) -> str:
    parsed = _parse(value)
    if parsed:
        return parsed.strftime("%Y-%m-%d")
    return inlineText(value) if value else NOT_RECORDED


def formatTimestamp(value) -> str:
    parsed = _parse(value)
    return parsed.strftime("%Y-%m-%d %H:%M UTC") if parsed else ""


def slugify(name) -> str:
    """A file-name-safe version of a business name: 'Café Mint — Plaza' becomes 'cafe-mint-plaza'."""
    folded = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-") or "target"


def analysisFileName(name: str) -> str:
    return f"reviewlens-{slugify(name)}-analysis.md"


def _linkText(url) -> str:
    if not url:
        return NOT_RECORDED
    return "<" + str(url).strip().replace(" ", "%20").replace("<", "%3C").replace(">", "%3E") + ">"


def buildAnalysisMarkdown(target: dict, summary: dict, history: list, exportedAt: datetime) -> str:
    """target: the analysis_targets row plus ingestion_status / ingestion_error / ingestion_skipped.
    summary: review_count and average_rating. history: qa_history rows, oldest first."""
    name = inlineText(target.get("business_name")) or "Untitled analysis"
    platformCode = target.get("platform")
    platform = PLATFORM_LABELS.get(platformCode, inlineText(platformCode) if platformCode else NOT_RECORDED)
    status = STATUS_LABELS.get(target.get("ingestion_status") or "not_started", "Not started")

    summary = summary or {}
    count = summary.get("review_count")
    average = summary.get("average_rating")
    skipped = target.get("ingestion_skipped")

    lines = [
        f"# ReviewLens analysis: {name}",
        "",
        "## Analysis",
        "",
        f"- **Name:** {name}",
        f"- **Review platform:** {platform}",
        f"- **Source:** {_linkText(target.get('source_url'))}",
        f"- **Created:** {formatDay(target.get('created_at'))}",
        f"- **Exported:** {exportedAt.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Ingestion summary",
        "",
        f"- **Latest run:** {status}",
        f"- **Stored reviews:** {'Not available' if count is None else count}",
        f"- **Average rating:** {'No ratings yet' if average is None else f'{float(average):.2f} / 5'}",
        f"- **Skipped in latest run:** {NOT_RECORDED if skipped is None else skipped}",
    ]
    if target.get("ingestion_status") == "failed" and target.get("ingestion_error"):
        lines.append(f"- **Error:** {inlineText(target['ingestion_error'])}")

    lines += ["", "## Q&A history", ""]
    if not history:
        lines.append("No questions have been asked about this analysis yet.")
    else:
        total = len(history)
        lines += [f"{total} question{'s' if total != 1 else ''} asked, oldest first.", "", EVIDENCE_NOTE]
        for number, entry in enumerate(history, start=1):
            asked = formatTimestamp(entry.get("created_at"))
            lines += ["", f"### Question {number}", ""]
            if asked:
                lines += [f"Asked: {asked}", ""]
            lines += ["**Question**", "", quoteBlock(entry.get("question")), "", "**Answer**", "", quoteBlock(entry.get("answer"))]

    return "\n".join(lines) + "\n"
