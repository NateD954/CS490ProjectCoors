import pytest
from app import main
from app.target_repository import saveTarget

URL = "https://www.google.com/maps/place/Chipotle/data=!1s0x89c2fa2bfb0d27d5:0xcceef158b20fbf10"


class FakeQuery:
    """Tiny in-memory stand-in for the Supabase query builder."""

    def __init__(self, rows):
        self.rows, self.filters, self.newRow, self.orderBy = rows, [], None, None

    def insert(self, row):
        self.newRow = row
        return self

    def select(self, *_):
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def in_(self, column, values):
        self.filters.append(lambda r: r.get(column) in values)
        return self

    def order(self, column, desc=False):
        self.orderBy = column
        return self

    def execute(self):
        if self.newRow is not None:
            self.rows.append({"id": f"id-{len(self.rows)}", "created_at": "2026-11-02T00:00:00Z", **self.newRow})
            data = [self.rows[-1]]
        else:
            data = [r for r in self.rows if all(f(r) for f in self.filters)]
        return type("Result", (), {"data": data})()


class FakeClient:
    def __init__(self):
        self.tables = {"analysis_targets": [], "ingestion_jobs": []}

    def table(self, name):
        return FakeQuery(self.tables[name])


@pytest.fixture
def client(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(main, "supabaseClient", fake)
    saveTarget(fake, "user_A", "0x1:0x2", "A's Cafe", URL)
    saveTarget(fake, "user_B", "0x3:0x4", "B's Bakery", URL)
    return fake


def names(userId):
    return [t["business_name"] for t in main.listTargets(userId)]


def test_user_a_sees_their_own_targets(client):
    assert names("user_A") == ["A's Cafe"]


def test_user_b_sees_their_own_targets(client):
    assert names("user_B") == ["B's Bakery"]


def test_user_b_does_not_receive_user_as_targets(client):
    assert "A's Cafe" not in names("user_B")
