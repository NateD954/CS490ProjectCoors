"""S3-013: supporting reviews shown with grounded answers (rules S3-BR-020 to S3-BR-022).

The model only names review tags. Everything shown to the user is read from the stored reviews
of the active target. No real model or database is used.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import main

OWNER = "user_A"


class Query:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.new = None

    def select(self, *_):
        return self

    def order(self, *_, **__):
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def in_(self, column, values):
        self.filters.append(lambda r: r.get(column) in values)
        return self

    def insert(self, row):
        self.new = row
        return self

    def execute(self):
        if self.new is not None:
            saved = {"id": f"qa-{len(self.rows) + 1}", **self.new}
            self.rows.append(saved)
            return SimpleNamespace(data=[dict(saved)])
        return SimpleNamespace(data=[dict(r) for r in self.rows if all(f(r) for f in self.filters)])


class Database:
    def __init__(self):
        self.tables = {"analysis_targets": [], "reviews": [], "qa_history": []}

    def table(self, name):
        return Query(self.tables[name])


class Evidence:
    def __init__(self, monkeypatch):
        self.db = Database()
        monkeypatch.setattr(main, "supabaseClient", self.db)
        main.app.dependency_overrides[main.getCurrentUserId] = lambda: OWNER
        self.client = TestClient(main.app)

    def add_target(self, targetId, *texts, owner=OWNER):
        self.db.tables["analysis_targets"].append(
            {"id": targetId, "owner_clerk_id": owner, "business_name": targetId, "platform": "GOOGLE_MAPS"}
        )
        for number, text in enumerate(texts, start=1):
            self.db.tables["reviews"].append({
                "id": f"{targetId}-review-{number}",
                "analysis_target_id": targetId,
                "review_text": text,
                "rating": number % 5 + 1,
                "reviewed_at": f"2026-01-0{number}T00:00:00+00:00",
                "google_review_id": f"g-{targetId}-{number}",
            })
        return targetId

    def ask(self, targetId):
        response = self.client.post(f"/api/targets/{targetId}/ask", json={"question": "What do people like?"})
        assert response.status_code == 200, response.text
        return response.json()

    def history(self, targetId):
        response = self.client.get(f"/api/targets/{targetId}/history")
        assert response.status_code == 200, response.text
        return response.json()


@pytest.fixture
def app(monkeypatch):
    yield Evidence(monkeypatch)
    main.app.dependency_overrides.clear()


CAFE = ["Great espresso", "Friendly staff", "Slow on weekends", "Fresh pastries", "Cozy seating", "Fair prices"]


def test_cited_reviews_are_returned_from_the_database_and_the_evidence_line_is_removed(app, model):
    cafe = app.add_target("cafe", *CAFE)
    model.will_answer('People love the coffee. One said "best espresso in town".\nEVIDENCE: R1, R4')

    result = app.ask(cafe)

    assert result["answer"] == 'People love the coffee. One said "best espresso in town".'
    assert result["supporting_reviews"] == [
        {"id": "cafe-review-1", "rating": 2, "review_text": "Great espresso", "reviewed_at": "2026-01-01T00:00:00+00:00"},
        {"id": "cafe-review-4", "rating": 5, "review_text": "Fresh pastries", "reviewed_at": "2026-01-04T00:00:00+00:00"},
    ]


def test_the_model_is_sent_a_tag_for_each_review_and_asked_for_plain_text(app, model):
    app.ask(app.add_target("cafe", *CAFE))

    assert "- Great espresso [R1]" in model.prompt_text
    assert "- Fair prices [R6]" in model.prompt_text
    assert "EVIDENCE:" in model.system_text
    assert "plain text only" in model.system_text


def test_unknown_tags_and_reviews_of_other_targets_are_rejected(app, model):
    cafe = app.add_target("cafe", "Great espresso", "Friendly staff")
    app.add_target("bakery", "Bakery secret")
    model.will_answer("They like it.\nEVIDENCE: R2, R3, R99, R0, bakery-review-1, made-up")

    result = app.ask(cafe)

    assert [r["id"] for r in result["supporting_reviews"]] == ["cafe-review-2"]
    assert "Bakery secret" not in str(result)


def test_at_most_five_reviews_are_shown_and_repeats_are_ignored(app, model):
    cafe = app.add_target("cafe", *CAFE)
    model.will_answer("Lots to like.\nEVIDENCE: R1, R1, R2, R3, R4, R5, R6")

    ids = [r["id"] for r in app.ask(cafe)["supporting_reviews"]]

    assert ids == [f"cafe-review-{n}" for n in (1, 2, 3, 4, 5)]


@pytest.mark.parametrize("answer", ["Nothing on parking.\nEVIDENCE: none", "Nothing on parking.", "Hm.\nEVIDENCE: R42"])
def test_no_evidence_is_shown_when_none_is_valid(app, model, answer):
    cafe = app.add_target("cafe", *CAFE)
    model.will_answer(answer)

    result = app.ask(cafe)

    assert result["answer"] == answer.split("\nEVIDENCE")[0]
    assert result["supporting_reviews"] == []


def test_only_review_ids_are_saved_and_history_reads_the_reviews_again(app, model):
    cafe = app.add_target("cafe", *CAFE)
    model.will_answer("People love the coffee.\nEVIDENCE: R1, R2")
    app.ask(cafe)

    saved = app.db.tables["qa_history"][0]
    assert saved["supporting_review_ids"] == ["cafe-review-1", "cafe-review-2"]
    assert saved["answer"] == "People love the coffee."
    assert "Great espresso" not in str(saved)  # no review text is copied into the history

    app.db.tables["reviews"][0]["review_text"] = "Great espresso (edited by a refresh)"
    entry = app.history(cafe)[0]

    assert [r["review_text"] for r in entry["supporting_reviews"]] == ["Great espresso (edited by a refresh)", "Friendly staff"]
    assert "supporting_review_ids" not in entry


def test_history_drops_saved_ids_that_are_missing_or_belong_to_another_target(app):
    cafe = app.add_target("cafe", "Great espresso")
    app.add_target("bakery", "Bakery secret")
    app.db.tables["qa_history"] += [
        {"id": "qa-1", "analysis_target_id": cafe, "question": "Q1", "answer": "A1",
         "supporting_review_ids": ["bakery-review-1", "deleted-review", "cafe-review-1"]},
        {"id": "qa-2", "analysis_target_id": cafe, "question": "Q2", "answer": "A2"},  # saved before S3-013
    ]

    first, second = app.history(cafe)

    assert [r["id"] for r in first["supporting_reviews"]] == ["cafe-review-1"]
    assert second["supporting_reviews"] == []
    assert "Bakery secret" not in str([first, second])
