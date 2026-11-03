import pytest
from app import main

URL = "https://www.google.com/maps/place/Chipotle/data=!1s0x89c2fa2bfb0d27d5:0xcceef158b20fbf10"


class FakeQuery:
    """Tiny in-memory stand-in for the Supabase query builder."""

    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.newRow = None
        self.changes = None

    def insert(self, row):
        self.newRow = row
        return self

    def update(self, changes):
        self.changes = changes
        return self

    def select(self, *_):
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def order(self, *_, **__):
        return self

    def range(self, *_):
        return self

    def execute(self):
        if self.newRow is not None:
            saved = {"id": f"id-{len(self.rows) + 1}", **self.newRow}
            self.rows.append(saved)
            data = [saved]
        else:
            data = [r for r in self.rows if all(f(r) for f in self.filters)]
            if self.changes is not None:
                for r in data:
                    r.update(self.changes)
        return type("Result", (), {"data": data})()


class FakeClient:
    def __init__(self):
        self.tables = {"analysis_targets": [], "ingestion_jobs": [], "reviews": []}

    def table(self, name):
        return FakeQuery(self.tables[name])


@pytest.fixture
def client(monkeypatch):
    """One target owned by user_A, with one stored review."""
    fake = FakeClient()
    fake.tables["analysis_targets"].append(
        {"id": "target-A", "owner_clerk_id": "user_A", "business_name": "A's Cafe", "source_url": URL}
    )
    fake.tables["reviews"].append(
        {
            "id": "review-1",
            "analysis_target_id": "target-A",
            "rating": 5,
            "review_text": "Secret review text",
            "reviewed_at": "2026-11-01T00:00:00Z",
        }
    )
    monkeypatch.setattr(main, "supabaseClient", fake)
    return fake


# ---- ingestion ---------------------------------------------------------------


def test_owner_can_start_ingestion(client, monkeypatch):
    # Control test: proves the setup works, so the denial below is really about ownership.
    monkeypatch.setattr(main, "getGooglePlaceData", lambda dataId: {"reviews": []})
    monkeypatch.setattr(main, "saveReviews", lambda rows: None)

    result = main.ingestTarget("target-A", "user_A")

    assert result["status"] == "completed"
    assert len(client.tables["ingestion_jobs"]) == 1


def test_another_user_cannot_start_ingestion(client, monkeypatch):
    providerCalls = []
    saveCalls = []
    monkeypatch.setattr(main, "getGooglePlaceData", lambda dataId: providerCalls.append(dataId) or {"reviews": []})
    monkeypatch.setattr(main, "saveReviews", lambda rows: saveCalls.append(rows))

    with pytest.raises(main.HTTPException) as err:
        main.ingestTarget("target-A", "user_B")

    assert err.value.status_code in (403, 404)
    assert client.tables["ingestion_jobs"] == []  # no job was created
    assert providerCalls == []  # the review provider was never called
    assert saveCalls == []  # nothing was saved
    assert len(client.tables["reviews"]) == 1  # user_A's reviews are untouched


def test_ingesting_an_unknown_target_creates_no_job(client, monkeypatch):
    monkeypatch.setattr(main, "getGooglePlaceData", lambda dataId: {"reviews": []})

    with pytest.raises(main.HTTPException) as err:
        main.ingestTarget("does-not-exist", "user_A")

    assert err.value.status_code == 404
    assert client.tables["ingestion_jobs"] == []


# ---- reading reviews ---------------------------------------------------------


def test_owner_can_read_their_reviews(client):
    # limit and offset are passed explicitly because calling the endpoint directly
    # skips FastAPI, which would normally fill in their defaults.
    reviews = main.getTargetReviews("target-A", "user_A", limit=None, offset=0)

    assert [r["review_text"] for r in reviews] == ["Secret review text"]


def test_another_user_cannot_read_reviews(client):
    with pytest.raises(main.HTTPException) as err:
        main.getTargetReviews("target-A", "user_B", limit=None, offset=0)

    assert err.value.status_code in (403, 404)
    assert "Secret review text" not in str(err.value.detail)


def test_another_user_cannot_read_reviews_even_with_paging(client):
    with pytest.raises(main.HTTPException) as err:
        main.getTargetReviews("target-A", "user_B", limit=5, offset=0)

    assert err.value.status_code in (403, 404)
