from copy import deepcopy

import pytest
import requests
from fastapi.testclient import TestClient

from app import main
from app import review_refresh
from test_integration_flows import FakeDatabase, FakeResponse, raw, CAFE_ID


@pytest.fixture
def refresh(monkeypatch, model):
    db = FakeDatabase()
    db.tables["qa_history"] = []
    monkeypatch.setattr(main, "supabaseClient", db)
    main.app.dependency_overrides[main.getCurrentUserId] = lambda: "user_A"
    client = TestClient(main.app)
    created = client.post("/api/targets", json={
        "name": "Cafe", "platform": "GOOGLE_MAPS",
        "sourceUrl": f"https://google.com/maps/data=!1s{CAFE_ID}",
    }).json()
    targetId = created["id"]
    batch = {"reviews": []}
    monkeypatch.setattr(main, "getGooglePlaceData", lambda _: batch)

    class Refresh:
        def ingest(self, reviews):
            batch["reviews"] = reviews
            return client.post(f"/api/targets/{targetId}/ingest")

        def target(self):
            return client.get(f"/api/targets/{targetId}").json()

    harness = Refresh()
    harness.db, harness.client, harness.targetId = db, client, targetId
    yield harness
    main.app.dependency_overrides.clear()


def test_partial_batches_promote_the_union_to_summary_browsing_qa_and_exports(refresh, model):
    assert refresh.ingest([
        raw("old", 3, "Kept from earlier ingestion", "2026-11-01"),
        raw("edited", 5, "Old wording", "2026-11-02"),
    ]).status_code == 200
    first = refresh.target()
    firstId = next(r["id"] for r in refresh.db.tables["reviews"] if r["google_review_id"] == "edited")

    assert refresh.ingest([
        raw("edited", 1, "Updated wording", "2026-11-02"),
        raw("new", 5, "Newly fetched review", "2026-11-03"),
    ]).status_code == 200
    current = refresh.target()
    assert current["id"] == first["id"]
    assert current["current_ingestion_id"] != first["current_ingestion_id"]
    assert current["current_ingestion_id"] == current["ingestion_id"]
    assert current["review_summary"] == {"review_count": 3, "average_rating": 3}
    assert len(refresh.db.tables["analysis_targets"]) == 1
    assert len(refresh.db.tables["ingestion_jobs"]) == 2

    url = f"/api/targets/{refresh.targetId}"
    reviews = refresh.client.get(url + "/reviews").json()
    assert {r["review_text"] for r in reviews} == {"Kept from earlier ingestion", "Updated wording", "Newly fetched review"}
    assert next(r["id"] for r in reviews if r["google_review_id"] == "edited") == firstId
    assert refresh.client.post(url + "/ask", json={"question": "What changed?"}).status_code == 200
    assert set(model.evidence) == {"Kept from earlier ingestion", "Updated wording", "Newly fetched review"}
    csv = refresh.client.get(url + "/reviews/export").text
    assert all(text in csv for text in model.evidence)
    assert "Old wording" not in csv
    markdown = refresh.client.get(url + "/export/markdown").text
    assert "**Stored reviews:** 3" in markdown
    assert "**Average rating:** 3.00 / 5" in markdown
    assert "**Last successful ingestion:**" in markdown


def test_duplicate_missing_ids_and_blank_ids_are_stable_across_batches(refresh):
    batch = [
        raw(None, 4, "No id here", "2026-11-01"),
        raw("  ", 4, "  NO   ID here  ", "2026-11-01"),
        raw("stable", 5, "Has an id", None),
        raw("stable", 5, "Same id twice", None),
    ]
    first = refresh.ingest(batch)
    assert first.status_code == 200
    assert first.json()["reviews_ingested"] == 2
    assert first.json()["reviews_skipped"] == 2
    savedIds = {r["id"] for r in refresh.db.tables["reviews"]}
    assert refresh.ingest(list(reversed(batch))).status_code == 200
    assert {r["id"] for r in refresh.db.tables["reviews"]} == savedIds
    assert refresh.target()["review_summary"]["review_count"] == 2


@pytest.mark.parametrize("failure", ["provider", "malformed", "unusable", "database"])
def test_failed_refresh_preserves_the_last_good_dataset_everywhere(refresh, monkeypatch, model, failure):
    refresh.ingest([raw("r1", 5, "Last good review", "2026-11-01")])
    savedReviews = deepcopy(refresh.db.tables["reviews"])
    savedTarget = refresh.target()
    if failure == "provider":
        def fail(_):
            raise requests.Timeout("secret provider details")
        monkeypatch.setattr(main, "getGooglePlaceData", fail)
    elif failure == "malformed":
        monkeypatch.setattr(main, "getGooglePlaceData", lambda _: {"unrelated": []})
    elif failure == "database":
        refresh.db.failPromotion = True

    result = refresh.ingest([None] if failure == "unusable" else [raw("r1", 1, "Uncommitted edit", None), raw("r2", 4, "Uncommitted new review", None)])
    assert result.status_code == 502
    assert "secret" not in result.text
    assert refresh.db.tables["reviews"] == savedReviews
    current = refresh.target()
    assert current["ingestion_status"] == "failed"
    assert current["ingestion_id"] != current["current_ingestion_id"]
    assert current["current_ingestion_id"] == savedTarget["current_ingestion_id"]
    assert current["current_ingestion_at"] == savedTarget["current_ingestion_at"]
    assert current["review_summary"] == {"review_count": 1, "average_rating": 5}
    assert refresh.db.tables["ingestion_jobs"][-1]["status"] == "failed"
    url = f"/api/targets/{refresh.targetId}"
    assert refresh.client.get(url + "/reviews").json() == savedReviews
    assert refresh.client.post(url + "/ask", json={"question": "What do people say?"}).status_code == 200
    assert model.evidence == ["Last good review"]
    assert "Last good review" in refresh.client.get(url + "/reviews/export").text


def test_empty_partial_batch_retains_all_stored_reviews(refresh):
    refresh.ingest([raw("r1", 5, "Saved review", None)])
    saved = deepcopy(refresh.db.tables["reviews"])
    assert refresh.ingest([]).status_code == 200
    assert refresh.db.tables["reviews"] == saved
    assert refresh.target()["review_summary"]["review_count"] == 1


def test_questions_prioritize_refreshed_reviews_when_the_dataset_exceeds_the_evidence_limit(refresh, model):
    refresh.ingest([raw(f"old-{i}", 3, f"Earlier review {i}", "2026-11-01") for i in range(60)])
    refresh.ingest([
        raw("old-0", 1, "Freshly updated review", "2026-11-01"),
        raw("new", 5, "New review after the first 60", "2026-11-02"),
    ])
    response = refresh.client.post(f"/api/targets/{refresh.targetId}/ask", json={"question": "What do people say?"})
    assert response.status_code == 200
    assert len(model.evidence) == 50
    assert "New review after the first 60" in model.evidence
    assert "Freshly updated review" in model.evidence
    assert "Earlier review 0" not in model.evidence
    assert refresh.target()["review_summary"]["review_count"] == 61


def test_overlapping_refresh_is_rejected_before_calling_the_provider(refresh, monkeypatch):
    job = review_refresh.beginIngestion(refresh.db, refresh.targetId)
    provider = []
    monkeypatch.setattr(main, "getGooglePlaceData", lambda _: provider.append(True))
    result = refresh.ingest([])
    assert result.status_code == 409
    assert "already running" in result.json()["detail"]
    assert provider == []
    assert len(refresh.db.tables["ingestion_jobs"]) == 1
    assert refresh.db.tables["ingestion_jobs"][0]["id"] == job["id"]


def test_start_failure_does_not_call_the_provider(refresh, monkeypatch):
    def fail(*_):
        raise ConnectionError("secret database details")
    monkeypatch.setattr(refresh.db, "rpc", fail)
    assert refresh.ingest([]).status_code == 503
    assert refresh.db.tables["ingestion_jobs"] == []


def test_dropped_completion_reply_retries_the_same_job_without_new_records(refresh, monkeypatch):
    rpc = refresh.db.rpc
    calls = []

    def loseReply(name, params):
        query = rpc(name, params)
        if name != "complete_review_ingestion":
            return query
        execute = query.execute
        def run():
            result = execute()
            calls.append(params["p_job_id"])
            if len(calls) == 1:
                raise ConnectionError("reply lost after commit")
            return result
        query.execute = run
        return query

    monkeypatch.setattr(refresh.db, "rpc", loseReply)
    assert refresh.ingest([raw(None, 5, "No duplicate after retry", None)]).status_code == 200
    assert len(calls) == 2 and calls[0] == calls[1]
    assert len(refresh.db.tables["reviews"]) == 1
    assert refresh.db.tables["ingestion_jobs"][0]["status"] == "completed"


def test_two_lost_replies_do_not_mark_a_committed_refresh_as_failed(refresh, monkeypatch):
    rpc = refresh.db.rpc
    def loseReply(name, params):
        query = rpc(name, params)
        if name == "complete_review_ingestion":
            execute = query.execute
            def run():
                execute()
                raise ConnectionError("reply lost")
            query.execute = run
        return query
    monkeypatch.setattr(refresh.db, "rpc", loseReply)
    result = refresh.ingest([raw("r1", 5, "Committed review", None)])
    assert result.status_code == 200
    assert result.json()["status"] == "completed"
    assert refresh.target()["ingestion_status"] == "completed"


def test_unavailable_job_status_returns_a_clear_retry_state(refresh, monkeypatch):
    def unavailable(*_):
        raise ConnectionError("database unavailable")
    monkeypatch.setattr(main, "failIngestion", unavailable)
    result = refresh.ingest([None])
    assert result.status_code == 503
    assert "Reload the target" in result.json()["detail"]


def test_provider_request_has_a_timeout(monkeypatch):
    from services import google_reviews
    calls = []
    def get(*args, **kwargs):
        calls.append(kwargs)
        return FakeResponse({"status": "OK", "data": {"reviews": []}})
    monkeypatch.setattr(google_reviews.requests, "get", get)
    google_reviews.getGooglePlaceData(CAFE_ID)
    assert calls[0]["timeout"] == 45


@pytest.mark.parametrize("sourceDate", ["2026-11-01", "2026-11-01T00:00:00Z", "2026-10-31T20:00:00-04:00"])
def test_source_dates_are_normalized_to_utc_for_the_same_identity(sourceDate):
    from services.google_reviews import parseReviews
    reviews, skipped = parseReviews({"reviews": [raw(None, 5, "Same review", sourceDate)]})
    assert reviews[0]["date"] == "2026-11-01T00:00:00+00:00"
    assert skipped == 0
