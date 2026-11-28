"""S3-004: a returning user reopens an analysis saved in an earlier session.

"A later session" here means a brand new client with nothing remembered: every fact
has to come back from what was saved in the database. Real HTTP requests go through
the real app (same setup as test_integration_flows.py).

Restored on reopen: name, source, ingestion state, stored reviews, ingestion summary.
Q&A history is covered by its own tests.
"""
import copy

import requests

# the fixtures and sample data are shared with the other integration tests
from test_integration_flows import (  # noqa: F401
    Api, CAFE_ID, CAFE_REVIEWS, FRONTEND_STATUSES, FakeDatabase, FakeQuery, api, provider, raw, reviewIds,
)
import pytest
from types import SimpleNamespace
from app import main


class Query(FakeQuery):
    """The shared fake, plus two things Save As needs from a real database: inserting a list
    of rows at once, and returning only the columns that were asked for."""

    columns = None

    def select(self, columns="*"):
        self.columns = None if columns == "*" else columns.split(",")
        return self

    def execute(self):
        if self.mode == "insert" and isinstance(self.payload, list):
            saved = [self.insertRow(r) for r in self.payload]
            return SimpleNamespace(data=[dict(r) for r in saved])
        result = super().execute()
        if self.mode == "select" and self.columns:
            result.data = [{c: r.get(c) for c in self.columns} for r in result.data]
        return result


class Database(FakeDatabase):
    def table(self, name):
        self.accessed.append(name)
        return Query(self, name)


@pytest.fixture
def db(monkeypatch):
    fake = Database()
    monkeypatch.setattr(main, "supabaseClient", fake)
    return fake


def saveInEarlierSession(api, provider, user="user_A", reviews=CAFE_REVIEWS):
    """Create an analysis and load its reviews, then forget everything the client knew."""
    provider.byPlace[CAFE_ID] = reviews
    target = api.asUser(user).create("Cafe", CAFE_ID)
    assert api.ingest(target["id"]).status_code == 200
    return target["id"]


def laterSession(user="user_A"):
    """A new client. It knows only the user's sign-in, nothing from before."""
    return Api().asUser(user)


# ---- what comes back ------------------------------------------------------------


def test_reopening_restores_the_name_and_the_source(api, db, provider):
    targetId = saveInEarlierSession(api, provider)
    before = api.target(targetId).json()

    reopened = laterSession().target(targetId)

    assert reopened.status_code == 200
    assert reopened.json()["business_name"] == "Cafe"
    assert reopened.json()["platform"] == "GOOGLE_MAPS"
    assert reopened.json()["source_url"] == before["source_url"]
    assert CAFE_ID in reopened.json()["source_url"]
    assert reopened.json()["google_place_id"] == CAFE_ID


def test_reopening_restores_the_ingestion_state_and_its_summary(api, db, provider):
    targetId = saveInEarlierSession(api, provider)
    before = api.target(targetId).json()

    reopened = laterSession().target(targetId).json()

    assert reopened["ingestion_status"] == before["ingestion_status"] == "partial"
    assert reopened["ingestion_skipped"] == before["ingestion_skipped"] == 2
    assert reopened["current_ingestion_id"] == before["current_ingestion_id"] is not None
    assert reopened["current_ingestion_at"] == before["current_ingestion_at"] is not None
    assert reopened["review_summary"] == before["review_summary"] == {"review_count": 3, "average_rating": 4}
    assert reopened["ingestion_status"] in FRONTEND_STATUSES


def test_reopening_restores_the_stored_review_dataset_in_the_same_order(api, db, provider):
    targetId = saveInEarlierSession(api, provider)
    before = api.reviews(targetId).json()

    after = laterSession().reviews(targetId)

    assert after.status_code == 200
    assert after.json() == before
    assert reviewIds(after) == ["r2", "r1", "r3"]


def test_paging_through_a_reopened_dataset_matches_the_first_session(api, db, provider):
    targetId = saveInEarlierSession(api, provider)
    first = [reviewIds(api.reviews(targetId, limit=2, offset=o)) for o in (0, 2)]

    later = laterSession()

    assert [reviewIds(later.reviews(targetId, limit=2, offset=o)) for o in (0, 2)] == first


def test_the_reopened_summary_matches_the_reopened_reviews(api, db, provider):
    targetId = saveInEarlierSession(api, provider)

    later = laterSession()
    stored = later.reviews(targetId).json()
    summary = later.target(targetId).json()["review_summary"]

    assert summary["review_count"] == len(stored)
    assert summary["average_rating"] == sum(r["rating"] for r in stored) / len(stored)


def test_the_analysis_is_in_the_returning_users_list(api, db, provider):
    targetId = saveInEarlierSession(api, provider)

    listed = laterSession().client.get("/api/targets").json()

    assert [t["id"] for t in listed] == [targetId]
    assert listed[0]["business_name"] == "Cafe"
    assert listed[0]["ingestion_status"] == "partial"


# ---- later changes are what come back ----------------------------------------------


def test_a_rename_in_an_earlier_session_is_what_reopens(api, db, provider):
    targetId = saveInEarlierSession(api, provider)
    api.client.patch(f"/api/targets/{targetId}", json={"name": "Corner cafe"})

    assert laterSession().target(targetId).json()["business_name"] == "Corner cafe"


def test_a_failed_refresh_reopens_with_the_failure_and_the_earlier_reviews(api, db, provider):
    targetId = saveInEarlierSession(api, provider)
    provider.error = requests.ConnectionError("provider is down")
    api.ingest(targetId)

    later = laterSession()
    reopened = later.target(targetId).json()

    assert reopened["ingestion_status"] == "failed"
    assert reopened["current_ingestion_id"] is not None  # the earlier good run is still the current one
    assert reopened["review_summary"] == {"review_count": 3, "average_rating": 4}
    assert reviewIds(later.reviews(targetId)) == ["r2", "r1", "r3"]


def test_a_refresh_in_an_earlier_session_is_what_reopens(api, db, provider):
    targetId = saveInEarlierSession(api, provider)
    provider.byPlace[CAFE_ID] = CAFE_REVIEWS + [raw("r9", 5, "Cafe added a new patio", "2026-10-09 10:00:00")]
    api.ingest(targetId)

    later = laterSession()

    assert reviewIds(later.reviews(targetId))[0] == "r9"
    assert later.target(targetId).json()["review_summary"]["review_count"] == 4


def test_an_analysis_that_was_never_ingested_reopens_empty_and_not_started(api, db, provider):
    targetId = api.asUser("user_A").create("Cafe", CAFE_ID)["id"]

    later = laterSession()
    reopened = later.target(targetId).json()

    assert reopened["business_name"] == "Cafe"
    assert reopened["ingestion_status"] == "not_started"
    assert reopened.get("current_ingestion_id") is None
    assert reopened["review_summary"] == {"review_count": 0, "average_rating": None}
    assert later.reviews(targetId).json() == []


def test_a_saved_copy_reopens_with_its_own_name_and_reviews(api, db, provider):
    targetId = saveInEarlierSession(api, provider)
    copy_ = api.client.post(f"/api/targets/{targetId}/save-as", json={"name": "Cafe (copy)"}).json()

    later = laterSession()
    reopened = later.target(copy_["id"]).json()

    assert reopened["business_name"] == "Cafe (copy)"
    assert reopened["ingestion_status"] == "partial"
    assert reopened["review_summary"] == {"review_count": 3, "average_rating": 4}
    assert reviewIds(later.reviews(copy_["id"])) == ["r2", "r1", "r3"]


# ---- reopening is only a read ------------------------------------------------------


def test_reopening_changes_nothing_in_the_database(api, db, provider):
    targetId = saveInEarlierSession(api, provider)
    saved = copy.deepcopy(db.tables)

    later = laterSession()
    later.target(targetId)
    later.reviews(targetId)
    later.client.get("/api/targets")

    assert db.tables == saved


def test_reopening_twice_gives_the_same_answer(api, db, provider):
    targetId = saveInEarlierSession(api, provider)

    first, second = laterSession().target(targetId).json(), laterSession().target(targetId).json()

    assert first == second


def test_reopening_makes_no_call_to_the_review_provider(api, db, provider):
    targetId = saveInEarlierSession(api, provider)
    calls = len(provider.calls)

    laterSession().target(targetId)

    assert len(provider.calls) == calls


# ---- only the owner ---------------------------------------------------------------


def test_another_user_cannot_reopen_the_analysis_or_read_its_reviews(api, db, provider):
    targetId = saveInEarlierSession(api, provider)

    other = laterSession("user_B")

    assert other.target(targetId).status_code == 403
    assert other.reviews(targetId).status_code == 403
    assert other.client.get("/api/targets").json() == []


def test_reopening_an_analysis_that_does_not_exist_is_a_404(api, db, provider):
    assert laterSession().target("00000000-0000-0000-0000-000000000000").status_code == 404
