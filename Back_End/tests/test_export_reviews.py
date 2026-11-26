"""Tests for GET /api/targets/{id}/reviews/export (S3-017: export the review dataset as CSV)."""

import csv
import io
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import main

COLUMNS = ["source_review_id", "rating", "review_text", "reviewed_at", "target_name", "platform", "target_source_url"]
URL = "https://www.google.com/maps/place/x/data=!1s0x1:0x2"


# ---- a small in-memory database ------------------------------------------------


class Query:
    def __init__(self, database, name):
        self.database = database
        self.rows = database.tables[name]
        self.filters = []
        self.orders = []
        self.window = None

    def select(self, *_):
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def order(self, column, desc=False, nullsfirst=False):
        self.orders.append((column, desc, nullsfirst))
        return self

    def range(self, start, end):
        self.window = (start, end)
        return self

    def execute(self):
        data = [dict(r) for r in self.rows if all(f(r) for f in self.filters)]
        for column, desc, nullsfirst in reversed(self.orders):
            present = sorted((r for r in data if r.get(column) is not None), key=lambda r: r[column], reverse=desc)
            missing = [r for r in data if r.get(column) is None]
            data = missing + present if nullsfirst else present + missing
        if self.window:
            start, end = self.window
            data = data[start : end + 1]
        return SimpleNamespace(data=data)


class Database:
    def __init__(self):
        self.tables = {"analysis_targets": [], "reviews": []}
        self.accessed = []

    def table(self, name):
        self.accessed.append(name)
        return Query(self, name)


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
            }
        )
        return targetId

    def add_review(self, targetId, reviewId, text="Nice", rating=5, date=None, sourceId="unset"):
        self.db.tables["reviews"].append(
            {
                "id": reviewId,
                "analysis_target_id": targetId,
                "google_review_id": reviewId if sourceId == "unset" else sourceId,
                "rating": rating,
                "review_text": text,
                "reviewed_at": date,
            }
        )

    def export(self, targetId, user="user_A"):
        if user is None:
            main.app.dependency_overrides.pop(main.getCurrentUserId, None)
        else:
            main.app.dependency_overrides[main.getCurrentUserId] = lambda: user
        return self.client.get(f"/api/targets/{targetId}/reviews/export")


@pytest.fixture
def exports(monkeypatch):
    app = ExportApp(monkeypatch)
    yield app
    main.app.dependency_overrides.clear()


def read_csv(response):
    text = response.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text, newline="")))


# ---- what is exported ----------------------------------------------------------


def test_the_owner_downloads_a_csv_of_the_stored_reviews_newest_first(exports):
    target = exports.add_target()
    exports.add_review(target, "r1", "Old review", 3, "2026-10-01T00:00:00+00:00")
    exports.add_review(target, "r2", "New review", 5, "2026-10-30T00:00:00+00:00")

    response = exports.export(target)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = read_csv(response)
    assert rows[0] == COLUMNS
    assert rows[1] == ["r2", "5", "New review", "2026-10-30T00:00:00+00:00", "Sample Cafe", "GOOGLE_MAPS", URL]
    assert rows[2] == ["r1", "3", "Old review", "2026-10-01T00:00:00+00:00", "Sample Cafe", "GOOGLE_MAPS", URL]
    assert len(rows) == 3


def test_the_file_is_utf8_with_a_marker_so_excel_shows_accents_correctly(exports):
    target = exports.add_target()
    exports.add_review(target, "r1", "Café ☕ is great")

    response = exports.export(target)

    assert response.content.startswith(b"\xef\xbb\xbf")
    assert read_csv(response)[1][2] == "Café ☕ is great"


def test_only_this_targets_reviews_are_exported(exports):
    mine = exports.add_target()
    other = exports.add_target(name="Other Place")
    exports.add_review(mine, "r1", "Mine")
    exports.add_review(other, "r2", "Not mine")

    rows = read_csv(exports.export(mine))

    assert [r[2] for r in rows[1:]] == ["Mine"]


def test_a_target_with_no_reviews_exports_just_the_header_row(exports):
    target = exports.add_target()

    response = exports.export(target)

    assert response.status_code == 200
    assert read_csv(response) == [COLUMNS]


def test_values_that_are_not_stored_stay_empty_and_are_not_invented(exports):
    target = exports.add_target()
    exports.add_review(target, "r1", "No date or source id", 4, None, sourceId=None)

    row = read_csv(exports.export(target))[1]

    assert row[0] == ""  # no source review identifier stored
    assert row[3] == ""  # no review date stored
    assert row[1] == "4"


def test_there_are_no_columns_for_data_the_database_does_not_keep(exports):
    header = read_csv(exports.export(exports.add_target()))[0]

    assert not any("author" in c or "reviewer" in c or "review_url" in c for c in header)


def test_undated_reviews_come_last(exports):
    target = exports.add_target()
    exports.add_review(target, "r1", "Undated", 3, None)
    exports.add_review(target, "r2", "Dated", 5, "2026-10-30T00:00:00+00:00")

    rows = read_csv(exports.export(target))

    assert [r[2] for r in rows[1:]] == ["Dated", "Undated"]


def test_every_review_is_exported_even_when_there_are_more_than_one_page(exports, monkeypatch):
    monkeypatch.setattr(main, "EXPORT_PAGE_SIZE", 10)
    target = exports.add_target()
    for day in range(1, 26):
        exports.add_review(target, f"r{day:02d}", f"Review {day}", 5, f"2026-10-{day:02d}T00:00:00+00:00")

    rows = read_csv(exports.export(target))

    assert len(rows) == 26  # header plus all 25 reviews
    assert rows[1][0] == "r25"
    assert rows[-1][0] == "r01"
    assert len({r[0] for r in rows[1:]}) == 25  # none repeated or skipped


# ---- cells are written safely ----------------------------------------------------


def test_commas_quotes_and_line_breaks_in_review_text_survive(exports):
    text = 'He said "great", twice\nsecond line'
    target = exports.add_target()
    exports.add_review(target, "r1", text)

    rows = read_csv(exports.export(target))

    assert len(rows) == 2
    assert rows[1][2] == text


@pytest.mark.parametrize("text", ['=HYPERLINK("http://evil.test","click")', "+1+1", "-2+3", "@SUM(A1)"])
def test_text_that_a_spreadsheet_could_run_as_a_formula_is_neutralised(exports, text):
    target = exports.add_target()
    exports.add_review(target, "r1", text)

    cell = read_csv(exports.export(target))[1][2]

    assert cell == "'" + text


def test_the_download_name_is_a_safe_file_name(exports):
    target = exports.add_target(name="Joe's Pizza & Pasta!")

    response = exports.export(target)

    assert response.headers["content-disposition"] == 'attachment; filename="reviewlens-joe-s-pizza-pasta-reviews.csv"'


# ---- who may export --------------------------------------------------------------


def test_another_user_cannot_export_a_target(exports):
    target = exports.add_target(owner="user_A")
    exports.add_review(target, "r1", "Secret review text")

    response = exports.export(target, user="user_B")

    assert response.status_code in (403, 404)
    assert "Secret review text" not in response.text
    assert "reviews" not in exports.db.accessed  # no review was even read


def test_exporting_an_unknown_target_is_not_found(exports):
    response = exports.export("does-not-exist")

    assert response.status_code == 404
    assert "reviews" not in exports.db.accessed


def test_a_request_without_a_login_is_refused_before_the_database_is_used(exports):
    target = exports.add_target()
    exports.add_review(target, "r1", "Secret review text")
    exports.db.accessed.clear()

    response = exports.export(target, user=None)

    assert response.status_code in (401, 403)
    assert "Secret review text" not in response.text
    assert exports.db.accessed == []
