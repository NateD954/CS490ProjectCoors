import pytest
from app import main
from test_integration_flows import FakeDatabase


def setupIngestion(monkeypatch):
    client = FakeDatabase()
    client.tables["analysis_targets"].append({"id": "target-1"})

    monkeypatch.setattr(main, "supabaseClient", client)
    monkeypatch.setattr(
        main,
        "verifyTargetOwnership",
        lambda targetId, userId: {"source_url": "fake-url"}
    )
    monkeypatch.setattr(
        main,
        "getGoogleDataIdFromURL",
        lambda url: "fake-data-id"
    )

    return client


def test_ingestion_completes(monkeypatch):
    client = setupIngestion(monkeypatch)

    monkeypatch.setattr(
        main,
        "getGooglePlaceData",
        lambda dataId: {
            "reviews": [{
                "review_id": "review-1",
                "rating": 5,
                "review_text": "Great place",
                "review_datetime_utc": "2026-10-31"
            }]
        }
    )

    result = main.ingestTarget("target-1", "user_A")

    assert result["status"] == "completed"
    assert result["reviews_ingested"] == 1
    assert client.tables["ingestion_jobs"][0]["status"] == "completed"


def test_ingestion_fails(monkeypatch):
    client = setupIngestion(monkeypatch)

    def fail(dataId):
        raise Exception("failed")

    monkeypatch.setattr(main, "getGooglePlaceData", fail)

    with pytest.raises(main.HTTPException):
        main.ingestTarget("target-1", "user_A")

    assert client.tables["ingestion_jobs"][0]["status"] == "failed"