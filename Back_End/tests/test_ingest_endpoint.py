import pytest
from app import main


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.row = None
        self.jobId = None

    def insert(self, row):
        self.row = {"id": "job-1", **row}
        return self

    def update(self, row):
        self.row = row
        return self

    def eq(self, column, value):
        self.jobId = value
        return self

    def execute(self):
        if self.jobId is None:
            self.rows.append(self.row)
            saved = self.rows[-1]
        else:
            saved = next(row for row in self.rows if row["id"] == self.jobId)
            saved.update(self.row)

        class Result:
            data = [saved]

        return Result()


class FakeClient:
    def __init__(self):
        self.jobs = []

    def table(self, name):
        return FakeQuery(self.jobs)


def setupIngestion(monkeypatch):
    client = FakeClient()

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
    monkeypatch.setattr(main, "saveReviews", lambda rows: None)

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
                "snippet": "Great place",
                "iso_date": "2026-10-31"
            }]
        }
    )

    result = main.ingestTarget("target-1", "user_A")

    assert result["status"] == "completed"
    assert result["reviews_ingested"] == 1
    assert client.jobs[0]["status"] == "completed"


def test_ingestion_fails(monkeypatch):
    client = setupIngestion(monkeypatch)

    def fail(dataId):
        raise Exception("failed")

    monkeypatch.setattr(main, "getGooglePlaceData", fail)

    with pytest.raises(main.HTTPException):
        main.ingestTarget("target-1", "user_A")

    assert client.jobs[0]["status"] == "failed"