"""Integration tests for the Sprint 2 boundaries (S2-002).

Unlike the unit tests, these do not call endpoint functions directly or replace
internal helpers. Each test sends real HTTP requests to the real FastAPI app, so the
routing, the ownership check, the repository code, the ingestion pipeline and the
Q&A code all run together. Only three things are replaced:

  * the login check (a request is treated as coming from the chosen user),
  * the database (an in-memory stand-in that behaves like Supabase for the calls
    this app makes: inserts, upserts, filters, ordering and paging),
  * the two outside services (the review provider and the AI provider), which are
    faked at the point where the HTTP request would leave the app.
"""

from datetime import datetime, timedelta, timezone

import pytest
import requests
from fastapi.testclient import TestClient

from app import main
from services import google_reviews

CAFE_ID = "0x1111111111111111:0xaaaaaaaaaaaaaaaa"
BAKERY_ID = "0x2222222222222222:0xbbbbbbbbbbbbbbbb"


# ---- in-memory database ------------------------------------------------------


def applyOrders(rows, orders):
    """Sort like Postgres does for chained .order() calls (last key first, stable)."""
    out = list(rows)
    for column, desc, nullsFirst in reversed(orders):
        present = [r for r in out if r.get(column) is not None]
        missing = [r for r in out if r.get(column) is None]
        present.sort(key=lambda r: r[column], reverse=desc)
        placeNullsFirst = nullsFirst if nullsFirst is not None else desc
        out = (missing + present) if placeNullsFirst else (present + missing)
    return out


class FakeQuery:
    def __init__(self, db, name):
        self.db = db
        self.name = name
        self.rows = db.tables[name]
        self.mode = "select"
        self.payload = None
        self.conflict = None
        self.filters = []
        self.orders = []
        self.window = None

    def select(self, *_):
        return self

    def insert(self, row):
        self.mode, self.payload = "insert", row
        return self

    def update(self, changes):
        self.mode, self.payload = "update", changes
        return self

    def upsert(self, rows, on_conflict=None):
        self.mode, self.payload, self.conflict = "upsert", rows, on_conflict
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def in_(self, column, values):
        self.filters.append(lambda r: r.get(column) in values)
        return self

    def order(self, column, desc=False, nullsfirst=None):
        self.orders.append((column, desc, nullsfirst))
        return self

    def range(self, start, end):
        self.window = (start, end)
        return self

    def matching(self):
        return [r for r in self.rows if all(f(r) for f in self.filters)]

    def insertRow(self, row):
        saved = {"id": self.db.newId(self.name), "created_at": self.db.stamp(), **row}
        self.rows.append(saved)
        return saved

    def upsertRow(self, row):
        keys = self.conflict.split(",")
        for existing in self.rows:
            if all(existing.get(k) == row.get(k) for k in keys):
                existing.update(row)
                return existing
        return self.insertRow(row)

    def execute(self):
        if self.mode == "insert":
            data = [self.insertRow(self.payload)]
        elif self.mode == "upsert":
            data = [self.upsertRow(r) for r in self.payload]
        elif self.mode == "update":
            data = self.matching()
            for r in data:
                r.update(self.payload)
        else:
            data = applyOrders(self.matching(), self.orders)
            if self.window:
                start, end = self.window
                data = data[start : end + 1]
        # Return copies, as a real database would, so callers cannot change stored rows.
        return type("Result", (), {"data": [dict(r) for r in data]})()


class FakeDatabase:
    def __init__(self):
        self.tables = {"analysis_targets": [], "ingestion_jobs": [], "reviews": []}
        self.accessed = []  # names of tables that were queried, in order
        self.clock = datetime.now(timezone.utc)
        self.ticks = 0

    def table(self, name):
        self.accessed.append(name)
        return FakeQuery(self, name)

    def stamp(self):
        self.ticks += 1
        return (self.clock + timedelta(milliseconds=self.ticks)).isoformat()

    def newId(self, name):
        return f"{name}-{len(self.tables[name]) + 1}"


# ---- fake outside services ---------------------------------------------------


class FakeResponse:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


class FakeReviewProvider:
    """The review provider: returns the raw reviews set up for each place id."""

    def __init__(self):
        self.byPlace = {}
        self.calls = []
        self.error = None

    def __call__(self, url, headers=None, params=None, **kwargs):
        place = params["business_id"]
        self.calls.append(place)
        if self.error:
            raise self.error
        return FakeResponse({"status": "OK", "data": {"reviews": self.byPlace.get(place, [])}})


class FakeAI:
    """The AI provider: records what it was sent and always gives the same answer."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse({"candidates": [{"content": {"parts": [{"text": "AI answer"}]}}]})

    def prompt(self, index=-1):
        return self.calls[index]["json"]["contents"][0]["parts"][0]["text"]


def raw(reviewId, rating, text, date):
    """A review as the provider sends it."""
    return {
        "review_id": reviewId,
        "rating": rating,
        "review_text": text,
        "review_datetime_utc": date,
        "author_name": "Someone",
    }


# ---- fixtures and helpers ----------------------------------------------------


@pytest.fixture
def db(monkeypatch):
    fake = FakeDatabase()
    monkeypatch.setattr(main, "supabaseClient", fake)
    return fake


@pytest.fixture
def provider(monkeypatch):
    fake = FakeReviewProvider()
    monkeypatch.setattr(google_reviews.requests, "get", fake)
    return fake


@pytest.fixture
def ai(monkeypatch):
    fake = FakeAI()
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(main.requests, "post", fake)
    return fake


class Api:
    """Sends requests to the real app, as whichever user was chosen last."""

    def __init__(self):
        self.client = TestClient(main.app)

    def asUser(self, userId):
        main.app.dependency_overrides[main.getCurrentUserId] = lambda: userId
        return self

    def create(self, name, placeId):
        url = f"https://www.google.com/maps/place/{name}/data=!1s{placeId}"
        res = self.client.post("/api/targets", json={"name": name, "platform": "GOOGLE_MAPS", "sourceUrl": url})
        assert res.status_code == 201, res.text
        return res.json()

    def ingest(self, targetId):
        return self.client.post(f"/api/targets/{targetId}/ingest")

    def target(self, targetId):
        return self.client.get(f"/api/targets/{targetId}")

    def reviews(self, targetId, **params):
        return self.client.get(f"/api/targets/{targetId}/reviews", params=params)

    def ask(self, targetId, question="What do people say?"):
        return self.client.post(f"/api/targets/{targetId}/ask", json={"question": question})


@pytest.fixture
def api():
    yield Api()
    main.app.dependency_overrides.clear()


def reviewIds(response):
    assert response.status_code == 200, response.text
    return [r["google_review_id"] for r in response.json()]


CAFE_REVIEWS = [
    raw("r1", 4, "Cafe pastries are fresh", "2026-10-01 10:00:00"),
    raw("r2", 5, "Cafe espresso is great", "2026-10-03 10:00:00"),
    raw("r3", 3, "Cafe has no date on this one", None),
    raw("r4", 6, "Rating out of range, must be skipped", "2026-10-04 10:00:00"),
    raw("r5", 5, None, "2026-10-05 10:00:00"),  # no text, must be skipped
]
BAKERY_REVIEWS = [raw("b1", 5, "Bakery sourdough is wonderful", "2026-10-02 10:00:00")]


# ---- 1. loading persisted reviews for an AnalysisTarget ----------------------


def test_ingested_reviews_are_stored_and_loaded_newest_first(api, db, provider):
    provider.byPlace[CAFE_ID] = CAFE_REVIEWS
    api.asUser("user_A")
    target = api.create("Cafe", CAFE_ID)

    job = api.ingest(target["id"])

    assert job.status_code == 200
    assert job.json()["status"] == "completed"
    assert job.json()["reviews_ingested"] == 3  # the invalid rating and the empty text were skipped
    # Newest first, with the undated review last.
    assert reviewIds(api.reviews(target["id"])) == ["r2", "r1", "r3"]
    assert {r["analysis_target_id"] for r in db.tables["reviews"]} == {target["id"]}


def test_paging_through_stored_reviews_is_consistent(api, db, provider):
    provider.byPlace[CAFE_ID] = CAFE_REVIEWS
    api.asUser("user_A")
    target = api.create("Cafe", CAFE_ID)
    api.ingest(target["id"])

    firstPage = reviewIds(api.reviews(target["id"], limit=2, offset=0))
    secondPage = reviewIds(api.reviews(target["id"], limit=2, offset=2))

    assert firstPage == ["r2", "r1"]
    assert secondPage == ["r3"]


def test_ingestion_status_is_reported_with_the_target(api, db, provider):
    provider.byPlace[CAFE_ID] = CAFE_REVIEWS
    api.asUser("user_A")
    target = api.create("Cafe", CAFE_ID)
    assert api.target(target["id"]).json()["ingestion_status"] == "not_started"

    api.ingest(target["id"])

    loaded = api.target(target["id"]).json()
    assert loaded["ingestion_status"] == "completed"
    assert loaded["business_name"] == "Cafe"


def test_reingesting_updates_reviews_in_place_without_duplicates(api, db, provider, ai):
    provider.byPlace[CAFE_ID] = [raw("r1", 4, "Original wording", "2026-10-01 10:00:00")]
    api.asUser("user_A")
    target = api.create("Cafe", CAFE_ID)
    api.ingest(target["id"])

    provider.byPlace[CAFE_ID] = [raw("r1", 2, "Edited wording", "2026-10-01 10:00:00")]
    second = api.ingest(target["id"])

    assert second.json()["status"] == "completed"
    stored = api.reviews(target["id"]).json()
    assert len(stored) == 1  # same review id, so it was updated and not added again
    assert stored[0]["review_text"] == "Edited wording"
    assert stored[0]["rating"] == 2
    assert len(db.tables["ingestion_jobs"]) == 2
    # The next question is answered from the edited text, not the old text.
    api.ask(target["id"])
    assert "Edited wording" in ai.prompt()
    assert "Original wording" not in ai.prompt()


def test_a_failed_ingestion_keeps_existing_reviews_and_reports_the_failure(api, db, provider):
    provider.byPlace[CAFE_ID] = CAFE_REVIEWS
    api.asUser("user_A")
    target = api.create("Cafe", CAFE_ID)
    api.ingest(target["id"])

    provider.error = requests.ConnectionError("failed for url https://example.test/?key=secret-key")
    failed = api.ingest(target["id"])

    assert failed.status_code == 502
    assert failed.json()["detail"] == "Could not fetch reviews from the review provider. Please try again."
    assert "secret-key" not in failed.text
    loaded = api.target(target["id"]).json()
    assert loaded["ingestion_status"] == "failed"
    assert loaded["ingestion_error"] == "Could not fetch reviews from the review provider. Please try again."
    assert reviewIds(api.reviews(target["id"])) == ["r2", "r1", "r3"]  # nothing was lost

    provider.error = None
    assert api.ingest(target["id"]).status_code == 200
    assert api.target(target["id"]).json()["ingestion_status"] == "completed"


# ---- 4. applying authenticated ownership before review retrieval --------------


def test_another_user_is_denied_before_any_review_is_read(api, db, provider, ai):
    provider.byPlace[CAFE_ID] = CAFE_REVIEWS
    api.asUser("user_A")
    target = api.create("Cafe", CAFE_ID)
    api.ingest(target["id"])
    providerCallsBefore = len(provider.calls)

    api.asUser("user_B")
    db.accessed.clear()
    responses = [
        api.target(target["id"]),
        api.reviews(target["id"]),
        api.reviews(target["id"], limit=5, offset=0),
        api.ask(target["id"]),
        api.ingest(target["id"]),
    ]

    for response in responses:
        assert response.status_code in (403, 404)
        assert "Cafe espresso is great" not in response.text
    assert "reviews" not in db.accessed  # the ownership check ran before any review lookup
    assert "ingestion_jobs" not in db.accessed  # and before any job was created
    assert len(db.tables["ingestion_jobs"]) == 1  # only user_A's job exists
    assert ai.calls == []  # the AI provider never saw user_A's reviews
    assert len(provider.calls) == providerCallsBefore  # and the review provider was not called again
    assert api.client.get("/api/targets").json() == []  # user_B's own list is empty


def test_requests_without_a_login_are_rejected_before_the_database_is_touched(api, db, provider, ai):
    # No user is chosen, so the real login check runs and finds no token.
    responses = [
        api.client.get("/api/targets"),
        api.client.get("/api/targets/some-id"),
        api.client.get("/api/targets/some-id/reviews"),
        api.client.post("/api/targets/some-id/ingest"),
        api.client.post("/api/targets/some-id/ask", json={"question": "Hello?"}),
        api.client.post("/api/targets", json={"name": "X", "platform": "GOOGLE_MAPS", "sourceUrl": "https://google.com"}),
    ]

    for response in responses:
        assert response.status_code in (401, 403)
    assert db.accessed == []
    assert ai.calls == []
    assert provider.calls == []


# ---- 3. passing the correct review dataset into the Q&A service ---------------


def test_a_question_is_answered_from_the_selected_targets_reviews_only(api, db, provider, ai):
    provider.byPlace[CAFE_ID] = CAFE_REVIEWS
    provider.byPlace[BAKERY_ID] = BAKERY_REVIEWS
    api.asUser("user_A")
    cafe = api.create("Cafe", CAFE_ID)
    bakery = api.create("Bakery", BAKERY_ID)
    api.ingest(cafe["id"])
    api.ingest(bakery["id"])

    response = api.ask(cafe["id"], "What do people say about the espresso?")

    assert response.status_code == 200
    assert response.json() == {"answer": "AI answer"}
    prompt = ai.prompt()
    assert "Cafe espresso is great" in prompt
    assert "Cafe pastries are fresh" in prompt
    assert "What do people say about the espresso?" in prompt
    assert "Bakery sourdough is wonderful" not in prompt  # the other target's reviews stay out
    assert "Rating out of range" not in prompt  # skipped at ingestion, so never stored or sent
    assert ai.calls[-1]["json"]["systemInstruction"]  # the evidence-only instructions are always sent


def test_a_question_on_a_target_with_no_reviews_does_not_call_the_ai_provider(api, db, provider, ai):
    api.asUser("user_A")
    target = api.create("Cafe", CAFE_ID)

    response = api.ask(target["id"])

    assert response.status_code == 200
    assert "No reviews have been ingested" in response.json()["answer"]
    assert ai.calls == []


# ---- 5. changing the active target and retrieving different data ---------------


def test_switching_between_targets_returns_each_targets_own_data(api, db, provider, ai):
    provider.byPlace[CAFE_ID] = CAFE_REVIEWS
    provider.byPlace[BAKERY_ID] = BAKERY_REVIEWS
    api.asUser("user_A")
    cafe = api.create("Cafe", CAFE_ID)
    bakery = api.create("Bakery", BAKERY_ID)
    api.ingest(cafe["id"])
    api.ingest(bakery["id"])

    assert reviewIds(api.reviews(cafe["id"])) == ["r2", "r1", "r3"]
    assert reviewIds(api.reviews(bakery["id"])) == ["b1"]

    api.ask(bakery["id"])
    assert "Bakery sourdough is wonderful" in ai.prompt()
    assert "Cafe espresso is great" not in ai.prompt()

    api.ask(cafe["id"])  # switching back must not carry anything over from the bakery
    assert "Cafe espresso is great" in ai.prompt()
    assert "Bakery sourdough is wonderful" not in ai.prompt()

    assert reviewIds(api.reviews(cafe["id"])) == ["r2", "r1", "r3"]  # and the first target is unchanged
    counts = {t["analysis_target_id"] for t in db.tables["reviews"]}
    assert counts == {cafe["id"], bakery["id"]}


def test_each_users_targets_stay_separate_when_both_use_the_app(api, db, provider, ai):
    provider.byPlace[CAFE_ID] = CAFE_REVIEWS
    provider.byPlace[BAKERY_ID] = BAKERY_REVIEWS
    cafe = api.asUser("user_A").create("Cafe", CAFE_ID)
    api.ingest(cafe["id"])
    bakery = api.asUser("user_B").create("Bakery", BAKERY_ID)
    api.ingest(bakery["id"])

    api.asUser("user_A")
    assert [t["business_name"] for t in api.client.get("/api/targets").json()] == ["Cafe"]
    assert reviewIds(api.reviews(cafe["id"])) == ["r2", "r1", "r3"]

    api.asUser("user_B")
    assert [t["business_name"] for t in api.client.get("/api/targets").json()] == ["Bakery"]
    assert reviewIds(api.reviews(bakery["id"])) == ["b1"]
    assert api.reviews(cafe["id"]).status_code in (403, 404)
