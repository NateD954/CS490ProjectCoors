from types import SimpleNamespace

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

    def select(self, *_):
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def insert(self, row):
        self.row = {"id": f"comparison-{len(self.rows) + 1}", "created_at": "2026-11-26T00:00:00Z", **row}
        return self

    def execute(self):
        if self.row is not None:
            self.rows.append(self.row)
            return SimpleNamespace(data=[self.row])
        return SimpleNamespace(data=[dict(r) for r in self.rows if all(f(r) for f in self.filters)])


class FakeClient:
    def __init__(self):
        self.tables = {
            "analysis_targets": [
                {"id": TARGET_A, "owner_clerk_id": "user_A"},
                {"id": TARGET_B, "owner_clerk_id": "user_A"},
                {"id": OTHER_USERS_TARGET, "owner_clerk_id": "user_B"},
            ],
            "comparisons": [],
        }

    @property
    def comparisons(self):
        return self.tables["comparisons"]

    def table(self, name):
        return FakeQuery(self.tables[name])


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
