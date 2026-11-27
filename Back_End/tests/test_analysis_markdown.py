"""Tests for the Markdown analysis export (S3-018): GET /api/targets/{id}/export/markdown."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import main
from app.analysis_export import (
    EVIDENCE_NOTE,
    analysisFileName,
    buildAnalysisMarkdown,
    formatDay,
    formatTimestamp,
    inlineText,
    quoteBlock,
)

URL = "https://www.google.com/maps/place/x/data=!1s0x1:0x2"
NOW = datetime(2026, 11, 26, 14, 3, tzinfo=timezone.utc)


# ---- pure functions --------------------------------------------------------------


def test_inline_text_escapes_markdown_characters_and_joins_lines():
    assert inlineText("Joe's *Pizza* <b>\nand_more") == "Joe's \\*Pizza\\* \\<b\\> and\\_more"


def test_quote_block_keeps_every_line_inside_the_quote():
    assert quoteBlock("# Heading\n\n- item\n<script>x</script>") == "> # Heading\n>\n> - item\n> \\<script>x\\</script>"


def test_quote_block_handles_windows_line_breaks_and_empty_text():
    assert quoteBlock("a\r\nb") == "> a\n> b"
    assert quoteBlock(None) == ">"


def test_timestamps_are_shown_in_utc_and_bad_values_do_not_crash():
    assert formatTimestamp("2026-11-26T09:01:00-05:00") == "2026-11-26 14:01 UTC"
    assert formatTimestamp("not a date") == ""
    assert formatDay("2026-11-17T04:20:00.123+00:00") == "2026-11-17"
    assert formatDay(None) == "Not recorded"


def test_the_file_name_is_a_safe_slug():
    assert analysisFileName("Joe's Pizza & Pasta!") == "reviewlens-joe-s-pizza-pasta-analysis.md"
    assert analysisFileName("***") == "reviewlens-target-analysis.md"
    assert analysisFileName("Café Blue Bottle — Mint Plaza") == "reviewlens-cafe-blue-bottle-mint-plaza-analysis.md"


def test_unknown_values_say_not_recorded_instead_of_being_invented():
    md = buildAnalysisMarkdown({"business_name": "Cafe"}, {"review_count": 0, "average_rating": None}, [], NOW)

    assert "- **Review platform:** Not recorded" in md
    assert "- **Source:** Not recorded" in md
    assert "- **Created:** Not recorded" in md
    assert "- **Average rating:** No ratings yet" in md
    assert "- **Skipped in latest run:** Not recorded" in md
    assert "- **Latest run:** Not started" in md


# ---- a small in-memory database ----------------------------------------------------


class Query:
    def __init__(self, database, name):
        self.rows = database.tables[name]
        self.filters = []
        self.orders = []

    def select(self, *_):
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def in_(self, column, values):
        self.filters.append(lambda r: r.get(column) in values)
        return self

    def order(self, column, desc=False, nullsfirst=False):
        self.orders.append((column, desc))
        return self

    def execute(self):
        data = [dict(r) for r in self.rows if all(f(r) for f in self.filters)]
        for column, desc in reversed(self.orders):
            data.sort(key=lambda r: r[column], reverse=desc)
        return SimpleNamespace(data=data)


class Database:
    def __init__(self):
        self.tables = {"analysis_targets": [], "reviews": [], "ingestion_jobs": [], "qa_history": []}
        self.accessed = []

    def table(self, name):
        self.accessed.append(name)
        return Query(self, name)

    def rpc(self, name, params):
        assert name == "get_target_review_summary"
        self.accessed.append("rpc")
        ratings = [r["rating"] for r in self.tables["reviews"] if r["analysis_target_id"] == params["target_id"]]
        row = {"review_count": len(ratings), "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None}
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=[row]))


class ExportApp:
    def __init__(self, monkeypatch):
        self.db = Database()
        monkeypatch.setattr(main, "supabaseClient", self.db)
        self.client = TestClient(main.app)
        self.counter = 0

    def add_target(self, owner="user_A", name="Sample Cafe"):
        self.counter += 1
        targetId = f"target-{self.counter}"
        self.db.tables["analysis_targets"].append(
            {
                "id": targetId,
                "owner_clerk_id": owner,
                "business_name": name,
                "platform": "GOOGLE_MAPS",
                "source_url": URL,
                "created_at": "2026-11-17T04:20:00.123+00:00",
            }
        )
        return targetId

    def add_review(self, targetId, rating):
        number = len(self.db.tables["reviews"]) + 1
        self.db.tables["reviews"].append({"id": f"r{number}", "analysis_target_id": targetId, "rating": rating})

    def add_job(self, targetId, status="completed", skipped=0, error=None):
        self.db.tables["ingestion_jobs"].append(
            {
                "id": f"job-{len(self.db.tables['ingestion_jobs']) + 1}",
                "analysis_target_id": targetId,
                "status": status,
                "reviews_skipped": skipped,
                "error_message": error,
                "created_at": "2026-11-26T10:00:00+00:00",
            }
        )

    def add_qa(self, targetId, question, answer, created="2026-11-26T14:01:00+00:00"):
        number = len(self.db.tables["qa_history"]) + 1
        self.db.tables["qa_history"].append(
            {"id": f"m{number:02d}", "analysis_target_id": targetId, "question": question, "answer": answer, "created_at": created}
        )

    def export(self, targetId, user="user_A"):
        if user is None:
            main.app.dependency_overrides.pop(main.getCurrentUserId, None)
        else:
            main.app.dependency_overrides[main.getCurrentUserId] = lambda: user
        return self.client.get(f"/api/targets/{targetId}/export/markdown")


@pytest.fixture
def exports(monkeypatch):
    app = ExportApp(monkeypatch)
    yield app
    main.app.dependency_overrides.clear()


# ---- the export ------------------------------------------------------------------------


def test_the_owner_downloads_a_markdown_file_with_the_analysis_details(exports):
    target = exports.add_target(name="Sample Cafe")

    response = exports.export(target)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == 'attachment; filename="reviewlens-sample-cafe-analysis.md"'
    md = response.text
    assert md.startswith("# ReviewLens analysis: Sample Cafe\n")
    assert "- **Name:** Sample Cafe" in md
    assert "- **Review platform:** Google Maps" in md
    assert f"- **Source:** <{URL}>" in md
    assert "- **Created:** 2026-11-17" in md
    assert "- **Exported:** " in md and md.count("UTC") >= 1


def test_the_ingestion_summary_comes_from_the_stored_data(exports):
    target = exports.add_target()
    for rating in (5, 4, 3):
        exports.add_review(target, rating)
    exports.add_job(target, status="completed", skipped=2)

    md = exports.export(target).text

    assert "- **Latest run:** Completed with skips" in md
    assert "- **Stored reviews:** 3" in md
    assert "- **Average rating:** 4.00 / 5" in md
    assert "- **Skipped in latest run:** 2" in md


def test_a_failed_run_shows_its_error_message(exports):
    target = exports.add_target()
    exports.add_job(target, status="failed", skipped=None, error="Provider down")

    md = exports.export(target).text

    assert "- **Latest run:** Failed" in md
    assert "- **Error:** Provider down" in md


def test_the_history_is_listed_oldest_first_with_questions_and_answers(exports):
    target = exports.add_target()
    exports.add_qa(target, "Second question?", "Second answer.", "2026-11-26T14:05:00+00:00")
    exports.add_qa(target, "First question?", "First answer.", "2026-11-26T14:01:00+00:00")

    md = exports.export(target).text

    assert "2 questions asked, oldest first." in md
    assert md.index("> First question?") < md.index("> Second question?")
    assert "### Question 1" in md and "### Question 2" in md
    assert "Asked: 2026-11-26 14:01 UTC" in md
    assert "> First answer." in md and "> Second answer." in md


def test_no_history_says_so_and_has_no_question_entries(exports):
    md = exports.export(exports.add_target()).text

    assert "No questions have been asked about this analysis yet." in md
    assert "### Question" not in md
    assert EVIDENCE_NOTE not in md


def test_the_file_says_plainly_that_per_answer_evidence_is_not_stored(exports):
    target = exports.add_target()
    exports.add_qa(target, "Q?", "A.")

    md = exports.export(target).text

    assert EVIDENCE_NOTE in md
    assert "Supporting evidence" not in md  # nothing is invented to fill a section


def test_only_this_targets_history_is_exported(exports):
    mine = exports.add_target()
    other = exports.add_target(name="Other Place")
    exports.add_qa(mine, "My question", "My answer")
    exports.add_qa(other, "Other question", "Other answer")

    md = exports.export(mine).text

    assert "My question" in md
    assert "Other question" not in md and "Other Place" not in md


def test_text_from_users_and_the_model_cannot_break_the_document(exports):
    target = exports.add_target(name="Joe's *Pizza* <b>")
    exports.add_qa(target, "# Fake heading\n<script>alert(1)</script>", "- a\n\n# not a heading")

    md = exports.export(target).text

    assert "# ReviewLens analysis: Joe's \\*Pizza\\* \\<b\\>" in md
    assert "> \\<script>alert(1)\\</script>" in md  # the < is escaped and the text stays inside the quote
    assert "\n<script>" not in md and "> <script>" not in md
    assert [line for line in md.split("\n") if line.startswith("# ")] == [
        "# ReviewLens analysis: Joe's \\*Pizza\\* \\<b\\>"
    ]
    assert "> # Fake heading" in md  # inside a quote, so it stays plain text


# ---- who may export --------------------------------------------------------------------


def test_another_user_cannot_export_a_target(exports):
    target = exports.add_target(owner="user_A")
    exports.add_qa(target, "Secret question", "Secret answer")

    response = exports.export(target, user="user_B")

    assert response.status_code in (403, 404)
    assert "Secret" not in response.text
    assert not {"qa_history", "reviews", "ingestion_jobs", "rpc"} & set(exports.db.accessed)


def test_exporting_an_unknown_target_is_not_found(exports):
    response = exports.export("does-not-exist")

    assert response.status_code == 404
    assert "qa_history" not in exports.db.accessed


def test_a_request_without_a_login_is_refused_before_the_database_is_used(exports):
    target = exports.add_target()
    exports.add_qa(target, "Secret question", "Secret answer")
    exports.db.accessed.clear()

    response = exports.export(target, user=None)

    assert response.status_code in (401, 403)
    assert "Secret" not in response.text
    assert exports.db.accessed == []
