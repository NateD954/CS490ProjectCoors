from types import SimpleNamespace
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import main

TARGET_A = "11111111-1111-1111-1111-111111111111"
TARGET_B = "22222222-2222-2222-2222-222222222222"
OTHER_USERS_TARGET = "33333333-3333-3333-3333-333333333333"
MISSING_TARGET = "44444444-4444-4444-4444-444444444444"


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.row = None
        self.orders = []
        self.maximum = None
        self.deleting = False
        self.offset = 0

    def select(self, *_):
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def insert(self, row):
        self.row = {"id": str(uuid4()), "created_at": "2026-11-26T00:00:00Z", **row}
        return self

    def in_(self, column, values):
        self.filters.append(lambda r: r.get(column) in values)
        return self

    def order(self, column, desc=False, nullsfirst=True):
        self.orders.append((column, desc, nullsfirst))
        return self

    def limit(self, maximum):
        self.maximum = maximum
        return self

    def range(self, start, end):
        self.offset = start
        self.maximum = end + 1
        return self

    def delete(self):
        self.deleting = True
        return self

    def execute(self):
        if self.row is not None:
            self.rows.append(self.row)
            return SimpleNamespace(data=[self.row])
        rows = [dict(r) for r in self.rows if all(f(r) for f in self.filters)]
        if self.deleting:
            self.rows[:] = [r for r in self.rows if not all(f(r) for f in self.filters)]
        for column, desc, nullsfirst in reversed(self.orders):
            present = sorted([r for r in rows if r.get(column) is not None], key=lambda r: r[column], reverse=desc)
            missing = [r for r in rows if r.get(column) is None]
            rows = missing + present if nullsfirst else present + missing
        return SimpleNamespace(data=rows[self.offset:self.maximum])


class FakeClient:
    def __init__(self):
        self.tables = {
            "analysis_targets": [
                {"id": TARGET_A, "owner_clerk_id": "user_A", "business_name": "Cafe A", "platform": "GOOGLE_MAPS", "source_url": "https://google.com/a"},
                {"id": TARGET_B, "owner_clerk_id": "user_A", "business_name": "Cafe B", "platform": "GOOGLE_MAPS", "source_url": "https://google.com/b"},
                {"id": OTHER_USERS_TARGET, "owner_clerk_id": "user_B", "business_name": "Private cafe"},
            ],
            "comparisons": [],
            "reviews": [
                {"id": f"review-{i}", "analysis_target_id": target, "rating": rating, "review_text": f"Review {i}", "reviewed_at": date}
                for i, target, rating, date in [
                    (1, TARGET_A, 5, "2026-11-20T00:00:00Z"),
                    (2, TARGET_A, 3, "2026-11-21T00:00:00Z"),
                    (3, TARGET_B, 2, None),
                ]
            ],
            "ingestion_jobs": [],
        }
        self.accessed = []

    @property
    def comparisons(self):
        return self.tables["comparisons"]

    def table(self, name):
        self.accessed.append(name)
        return FakeQuery(self.tables[name])

    def rpc(self, name, params):
        assert name == "get_target_review_summary"
        self.accessed.append("summary:" + params["target_id"])
        rows = [r for r in self.tables["reviews"] if r["analysis_target_id"] == params["target_id"]]
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=[{
            "review_count": len(rows),
            "average_rating": sum(r["rating"] for r in rows) / len(rows) if rows else None,
        }]))


@pytest.fixture
def db(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(main, "supabaseClient", fake)
    main.app.dependency_overrides[main.getCurrentUserId] = lambda: "user_A"
    yield fake
    main.app.dependency_overrides.clear()


def create(**overrides):
    body = {"name": "A vs B", "targetAId": TARGET_A, "targetBId": TARGET_B}
    body.update(overrides)
    return TestClient(main.app).post("/api/comparisons", json=body)


def test_valid_comparison_is_created_for_the_logged_in_user(db):
    response = create(name="  A vs B  ")

    assert response.status_code == 201
    assert response.json() == db.comparisons[0]
    assert len(db.comparisons) == 1
    saved = db.comparisons[0]
    assert saved["owner_clerk_id"] == "user_A"
    assert saved["name"] == "A vs B"
    assert saved["target_a_id"] == TARGET_A
    assert saved["target_b_id"] == TARGET_B


@pytest.mark.parametrize("name", ["", "   "])
def test_empty_name_is_rejected(db, name):
    response = create(name=name)

    assert response.status_code == 400
    assert db.comparisons == []


def test_identical_targets_are_rejected(db):
    response = create(targetBId=TARGET_A)

    assert response.status_code == 400
    assert db.comparisons == []


@pytest.mark.parametrize("field", ["targetAId", "targetBId"])
def test_nonexistent_target_is_rejected(db, field):
    response = create(**{field: MISSING_TARGET})

    assert response.status_code == 404
    assert db.comparisons == []


@pytest.mark.parametrize("field", ["targetAId", "targetBId"])
def test_target_owned_by_another_user_is_rejected(db, field):
    response = create(**{field: OTHER_USERS_TARGET})

    assert response.status_code == 403
    assert db.comparisons == []


@pytest.mark.parametrize("field", ["targetAId", "targetBId"])
def test_malformed_target_id_is_rejected(db, field):
    response = create(**{field: "not-a-uuid"})

    assert response.status_code == 422
    assert db.comparisons == []


def test_list_is_scoped_to_the_user_and_newest_first(db):
    older = create(name="Older").json()
    newer = create(name="Newer").json()
    db.comparisons[0]["created_at"] = "2026-11-01T00:00:00Z"
    db.comparisons.append({**newer, "id": str(uuid4()), "owner_clerk_id": "user_B", "name": "Private"})

    response = TestClient(main.app).get("/api/comparisons")

    assert response.status_code == 200
    assert [r["id"] for r in response.json()] == [newer["id"], older["id"]]


def test_empty_list(db):
    assert TestClient(main.app).get("/api/comparisons").json() == []


def test_list_returns_comparisons_beyond_the_database_page_limit(db):
    saved = create().json()
    db.tables["comparisons"] = [{**saved, "id": f"c{i:04}"} for i in range(1005)]

    response = TestClient(main.app).get("/api/comparisons")

    assert response.status_code == 200
    assert [r["id"] for r in response.json()] == [f"c{i:04}" for i in reversed(range(1005))]


def test_reopen_aggregates_both_persisted_datasets_and_latest_ingestion(db):
    saved = create().json()
    db.tables["ingestion_jobs"] = [
        {"id": "old", "analysis_target_id": TARGET_A, "status": "failed", "created_at": "2026-11-01T00:00:00Z"},
        {"id": "new", "analysis_target_id": TARGET_A, "status": "completed", "reviews_skipped": 1, "created_at": "2026-11-25T00:00:00Z"},
    ]

    response = TestClient(main.app).get(f"/api/comparisons/{saved['id']}")

    assert response.status_code == 200
    detail = response.json()
    assert detail["name"] == saved["name"]
    a, b = detail["target_a"], detail["target_b"]
    assert a["unavailable"] is False and b["unavailable"] is False
    assert a["business_name"] == "Cafe A" and b["business_name"] == "Cafe B"
    assert a["platform"] == "GOOGLE_MAPS" and a["source_url"] == "https://google.com/a"
    assert a["review_summary"] == {"review_count": 2, "average_rating": 4.0}
    assert b["review_summary"] == {"review_count": 1, "average_rating": 2.0}
    assert a["ingestion_status"] == "partial" and a["ingestion_skipped"] == 1
    assert b["ingestion_status"] == "not_started"
    assert [r["id"] for r in a["sample_reviews"]] == ["review-2", "review-1"]
    assert [r["id"] for r in b["sample_reviews"]] == ["review-3"]


def test_samples_are_bounded_and_summary_includes_all_reviews(db):
    saved = create().json()
    db.tables["reviews"] = [
        {"id": f"r{i:04}", "analysis_target_id": TARGET_A, "rating": 5, "reviewed_at": None, "review_text": "Good"}
        for i in range(1005)
    ]

    detail = TestClient(main.app).get(f"/api/comparisons/{saved['id']}").json()

    assert detail["target_a"]["review_summary"] == {"review_count": 1005, "average_rating": 5.0}
    assert len(detail["target_a"]["sample_reviews"]) == 3
    assert detail["target_b"]["review_summary"] == {"review_count": 0, "average_rating": None}
    assert detail["target_b"]["sample_reviews"] == []


@pytest.mark.parametrize("method", ["get", "delete"])
def test_other_users_comparison_is_rejected_before_reading_datasets(db, method):
    saved = create().json()
    main.app.dependency_overrides[main.getCurrentUserId] = lambda: "user_B"
    db.accessed.clear()

    response = getattr(TestClient(main.app), method)(f"/api/comparisons/{saved['id']}")

    assert response.status_code == 403
    assert db.accessed == ["comparisons"]
    assert len(db.comparisons) == 1


@pytest.mark.parametrize("method", ["get", "delete"])
def test_missing_comparison_is_404(db, method):
    assert getattr(TestClient(main.app), method)(f"/api/comparisons/{uuid4()}").status_code == 404


@pytest.mark.parametrize("method", ["get", "delete"])
def test_malformed_comparison_id_is_422(db, method):
    assert getattr(TestClient(main.app), method)("/api/comparisons/not-a-uuid").status_code == 422


@pytest.mark.parametrize("slots", [("a",), ("b",), ("a", "b")])
@pytest.mark.parametrize("missing_state", ["null", "missing", "unowned"])
def test_unavailable_analysis_keeps_the_other_side_readable(db, slots, missing_state):
    saved = create().json()
    for slot in slots:
        target_id = saved[f"target_{slot}_id"]
        if missing_state == "null":
            db.comparisons[0][f"target_{slot}_id"] = None
        elif missing_state == "missing":
            db.tables["analysis_targets"][:] = [t for t in db.tables["analysis_targets"] if t["id"] != target_id]
        else:
            next(t for t in db.tables["analysis_targets"] if t["id"] == target_id)["owner_clerk_id"] = "user_B"
    db.accessed.clear()

    response = TestClient(main.app).get(f"/api/comparisons/{saved['id']}")

    assert response.status_code == 200
    for slot in ("a", "b"):
        side = response.json()[f"target_{slot}"]
        assert side["unavailable"] is (slot in slots)
        if slot in slots:
            assert set(side) == {"id", "unavailable", "reason"}
            assert "summary:" + saved[f"target_{slot}_id"] not in db.accessed
        else:
            assert side["sample_reviews"]


@pytest.mark.parametrize("failure", [main.HTTPError("private connection details"), main.APIError({"message": "private DB details", "code": "XX000", "details": None, "hint": None})])
def test_temporary_dataset_failure_is_isolated_and_does_not_leak_details(db, monkeypatch, failure):
    saved = create().json()
    original = main.getReviewSummary

    def summary(client, target_id):
        if target_id == TARGET_A:
            raise failure
        return original(client, target_id)

    monkeypatch.setattr(main, "getReviewSummary", summary)
    response = TestClient(main.app).get(f"/api/comparisons/{saved['id']}")

    assert response.status_code == 200
    assert response.json()["target_a"]["reason"] == "temporarily_unavailable"
    assert response.json()["target_b"]["unavailable"] is False
    assert "private" not in response.text


def test_create_reopen_delete_keeps_targets_and_reviews(db):
    before = deepcopy({name: db.tables[name] for name in ("analysis_targets", "reviews", "ingestion_jobs")})
    client = TestClient(main.app)
    saved = create().json()
    assert client.get(f"/api/comparisons/{saved['id']}").status_code == 200

    response = client.delete(f"/api/comparisons/{saved['id']}")

    assert response.status_code == 204 and response.content == b""
    assert client.get("/api/comparisons").json() == []
    assert client.get(f"/api/comparisons/{saved['id']}").status_code == 404
    assert client.delete(f"/api/comparisons/{saved['id']}").status_code == 404
    assert all(db.tables[name] == rows for name, rows in before.items())


@pytest.mark.parametrize("method,path", [("get", "/api/comparisons"), ("get", f"/api/comparisons/{TARGET_A}"), ("delete", f"/api/comparisons/{TARGET_A}")])
def test_comparison_routes_require_authentication(db, method, path):
    main.app.dependency_overrides.clear()
    assert getattr(TestClient(main.app), method)(path).status_code == 401
