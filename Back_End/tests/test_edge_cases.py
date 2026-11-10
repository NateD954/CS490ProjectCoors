"""Tests for the error and edge-case paths that matter most.

Covers: ingestion failing on a link with no place id, the provider answering badly,
the review save retrying, stuck jobs being shown as failed, and link checking.
"""

from datetime import datetime, timedelta, timezone

import pytest
import requests

from app import main
from services import google_reviews
from services.google_reviews import getGoogleDataIdFromURL, getGooglePlaceData

PLACE_ID = "0x89c2fa2bfb0d27d5:0xcceef158b20fbf10"
GOOD_URL = f"https://www.google.com/maps/place/Cafe/data=!1s{PLACE_ID}!8m2"
NO_PLACE_ID_URL = "https://www.google.com/maps/place/Cafe"
PROVIDER_FAILED = "Could not fetch reviews from the review provider. Please try again."


# ---- a small in-memory database ----------------------------------------------


class MiniQuery:
    def __init__(self, db, name):
        self.db = db
        self.name = name
        self.rows = db.tables[name]
        self.mode = "select"
        self.payload = None
        self.filters = []
        self.sort = None

    def select(self, *_):
        return self

    def insert(self, row):
        self.mode, self.payload = "insert", row
        return self

    def update(self, changes):
        self.mode, self.payload = "update", changes
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def in_(self, column, values):
        self.filters.append(lambda r: r.get(column) in values)
        return self

    def order(self, column, desc=False, **_):
        self.sort = (column, desc)
        return self

    def execute(self):
        if self.mode == "insert":
            saved = {"id": f"{self.name}-{len(self.rows) + 1}", **self.payload}
            self.rows.append(saved)
            data = [saved]
        else:
            data = [r for r in self.rows if all(f(r) for f in self.filters)]
            if self.mode == "update":
                for r in data:
                    r.update(self.payload)
            elif self.sort:
                column, desc = self.sort
                data = sorted(data, key=lambda r: r[column], reverse=desc)
        return type("Result", (), {"data": [dict(r) for r in data]})()


class MiniDatabase:
    def __init__(self):
        self.tables = {"analysis_targets": [], "ingestion_jobs": [], "reviews": []}

    def table(self, name):
        return MiniQuery(self, name)


class FakeResponse:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


@pytest.fixture
def db(monkeypatch):
    fake = MiniDatabase()
    monkeypatch.setattr(main, "supabaseClient", fake)
    return fake


def addTarget(db, sourceUrl, owner="user_A"):
    db.tables["analysis_targets"].append(
        {"id": "t1", "owner_clerk_id": owner, "business_name": "Cafe", "source_url": sourceUrl}
    )


def providerReturns(monkeypatch, outcome):
    """Replace the outgoing request to the review provider."""
    calls = []

    def fakeGet(url, headers=None, params=None, **kwargs):
        calls.append({"url": url, "headers": headers, "params": params})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(google_reviews.requests, "get", fakeGet)
    return calls


# ---- ingestion: a link with no place id --------------------------------------


def test_ingestion_fails_cleanly_when_the_stored_link_has_no_place_id(db, monkeypatch):
    addTarget(db, NO_PLACE_ID_URL)
    providerCalls = []
    monkeypatch.setattr(main, "getGooglePlaceData", lambda dataId: providerCalls.append(dataId))
    message = "The target's source URL does not contain a Google Maps place id."

    with pytest.raises(main.HTTPException) as err:
        main.ingestTarget("t1", "user_A")

    assert err.value.status_code == 502
    assert err.value.detail == message
    job = db.tables["ingestion_jobs"][0]
    assert job["status"] == "failed"
    assert job["error_message"] == message
    assert providerCalls == []  # nothing was requested from the provider
    assert db.tables["reviews"] == []  # and no reviews were invented


# ---- ingestion: the provider or the database misbehaves ----------------------


def test_provider_answering_with_an_error_status_fails_the_job_safely(db, monkeypatch):
    addTarget(db, GOOD_URL)
    providerReturns(monkeypatch, FakeResponse({"status": "ERROR"}))

    with pytest.raises(main.HTTPException) as err:
        main.ingestTarget("t1", "user_A")

    assert err.value.status_code == 502
    assert err.value.detail == PROVIDER_FAILED
    assert "OpenWeb Ninja" not in str(err.value.detail)  # the provider's wording is not shown to users
    assert db.tables["ingestion_jobs"][0]["status"] == "failed"
    assert db.tables["reviews"] == []


def test_provider_http_error_fails_the_job_without_leaking_details(db, monkeypatch):
    addTarget(db, GOOD_URL)
    error = requests.HTTPError("500 Server Error for url: https://example.test/?key=secret-key")
    providerReturns(monkeypatch, FakeResponse(error=error))

    with pytest.raises(main.HTTPException) as err:
        main.ingestTarget("t1", "user_A")

    assert err.value.detail == PROVIDER_FAILED
    assert "secret-key" not in str(err.value.detail)
    assert db.tables["ingestion_jobs"][0]["error_message"] == PROVIDER_FAILED


def test_a_database_failure_while_saving_reviews_fails_the_job(db, monkeypatch):
    addTarget(db, GOOD_URL)
    providerReturns(
        monkeypatch,
        FakeResponse({"status": "OK", "data": {"reviews": [{"review_id": "r1", "rating": 5, "review_text": "Great"}]}}),
    )

    def failToSave(rows):
        raise RuntimeError("database is down")

    monkeypatch.setattr(main, "saveReviews", failToSave)

    with pytest.raises(main.HTTPException) as err:
        main.ingestTarget("t1", "user_A")

    assert err.value.status_code == 502
    assert err.value.detail == PROVIDER_FAILED
    assert db.tables["ingestion_jobs"][0]["status"] == "failed"


# ---- saving reviews retries once ---------------------------------------------


class FlakyReviewsClient:
    """Fails or succeeds on each save, in the order given. None means success."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.saves = []

    def table(self, name):
        assert name == "reviews"
        return self

    def upsert(self, rows, on_conflict=None):
        self.saves.append({"rows": rows, "on_conflict": on_conflict})
        return self

    def execute(self):
        outcome = self.outcomes.pop(0)
        if outcome:
            raise outcome


def test_saving_reviews_succeeds_on_the_second_try_after_a_dropped_connection(monkeypatch):
    client = FlakyReviewsClient([ConnectionError("connection dropped"), None])
    monkeypatch.setattr(main, "supabaseClient", client)
    rows = [{"analysis_target_id": "t1", "google_review_id": "r1"}]

    main.saveReviews(rows)  # must not raise

    assert len(client.saves) == 2
    assert client.saves[1]["rows"] == rows


def test_saving_reviews_gives_up_after_the_second_failure(monkeypatch):
    client = FlakyReviewsClient([ConnectionError("first"), ConnectionError("second")])
    monkeypatch.setattr(main, "supabaseClient", client)

    with pytest.raises(ConnectionError, match="second"):
        main.saveReviews([{"analysis_target_id": "t1", "google_review_id": "r1"}])

    assert len(client.saves) == 2  # tried exactly twice


def test_saving_reviews_updates_existing_ones_instead_of_duplicating(monkeypatch):
    client = FlakyReviewsClient([None])
    monkeypatch.setattr(main, "supabaseClient", client)

    main.saveReviews([{"analysis_target_id": "t1", "google_review_id": "r1"}])

    assert client.saves[0]["on_conflict"] == "analysis_target_id,google_review_id"


# ---- ingestion status shown with a target ------------------------------------


def minutesAgo(minutes):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def statusFor(db, *jobs):
    for i, job in enumerate(jobs):
        db.tables["ingestion_jobs"].append({"id": f"job-{i}", "analysis_target_id": "t1", **job})
    return main.withIngestionStatus([{"id": "t1"}])[0]


def test_a_job_stuck_for_over_ten_minutes_is_shown_as_failed_so_the_user_can_retry(db):
    target = statusFor(db, {"status": "running", "created_at": minutesAgo(11)})

    assert target["ingestion_status"] == "failed"
    assert target["ingestion_error"] == "Ingestion did not finish. You can try again."


def test_a_recent_running_job_is_shown_as_in_progress(db):
    target = statusFor(db, {"status": "running", "created_at": minutesAgo(2)})

    assert target["ingestion_status"] == "in_progress"
    assert target["ingestion_error"] is None


def test_a_pending_job_is_shown_as_in_progress(db):
    assert statusFor(db, {"status": "pending", "created_at": minutesAgo(1)})["ingestion_status"] == "in_progress"


def test_an_old_finished_job_is_not_treated_as_stuck(db):
    target = statusFor(db, {"status": "completed", "created_at": minutesAgo(120)})

    assert target["ingestion_status"] == "completed"


def test_a_failed_job_keeps_its_error_message(db):
    target = statusFor(db, {"status": "failed", "error_message": "Provider down", "created_at": minutesAgo(5)})

    assert target["ingestion_status"] == "failed"
    assert target["ingestion_error"] == "Provider down"


def test_the_newest_job_decides_the_state(db):
    target = statusFor(
        db,
        {"status": "failed", "error_message": "Old failure", "created_at": minutesAgo(60)},
        {"status": "completed", "created_at": minutesAgo(30)},
    )

    assert target["ingestion_status"] == "completed"
    assert target["ingestion_error"] is None


def test_an_unknown_job_status_counts_as_not_started(db):
    assert statusFor(db, {"status": "something-else", "created_at": minutesAgo(1)})["ingestion_status"] == "not_started"


def test_a_target_with_no_jobs_is_not_started(db):
    target = main.withIngestionStatus([{"id": "t1"}])[0]

    assert target["ingestion_status"] == "not_started"
    assert target["ingestion_error"] is None


def test_an_empty_list_of_targets_is_returned_unchanged(db):
    assert main.withIngestionStatus([]) == []


# ---- checking that a link is a Google link -----------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.google.com/maps/place/x", True),
        ("http://maps.google.com/x", True),
        ("https://google.com/maps", True),
        ("https://google.com.evil.com/maps", False),
        ("https://notgoogle.com/maps", False),
        ("ftp://www.google.com/maps", False),
        ("javascript:alert(1)", False),
        ("not a url", False),
        ("", False),
        ("http://[::1", False),  # cannot be parsed at all
    ],
)
def test_only_real_google_web_links_are_accepted(url, expected):
    assert main.isGoogleUrl(url) is expected


# ---- the review provider client ----------------------------------------------


def test_place_id_is_taken_from_the_link():
    assert getGoogleDataIdFromURL(GOOD_URL) == PLACE_ID


def test_a_link_without_a_place_id_gives_none():
    assert getGoogleDataIdFromURL(NO_PLACE_ID_URL) is None


def test_the_provider_is_asked_for_the_right_place_with_a_key(monkeypatch):
    payload = {"status": "OK", "data": {"reviews": [{"review_id": "r1"}]}}
    calls = providerReturns(monkeypatch, FakeResponse(payload))

    data = getGooglePlaceData(PLACE_ID)

    assert data == {"reviews": [{"review_id": "r1"}]}
    assert calls[0]["params"] == {"business_id": PLACE_ID, "limit": 25}
    assert "x-api-key" in calls[0]["headers"]


def test_a_provider_status_other_than_ok_is_an_error(monkeypatch):
    providerReturns(monkeypatch, FakeResponse({"status": "ERROR"}))

    with pytest.raises(Exception, match="Error from OpenWeb Ninja"):
        getGooglePlaceData(PLACE_ID)


def test_a_provider_http_error_is_passed_on(monkeypatch):
    providerReturns(monkeypatch, FakeResponse(error=requests.HTTPError("503")))

    with pytest.raises(requests.HTTPError):
        getGooglePlaceData(PLACE_ID)
