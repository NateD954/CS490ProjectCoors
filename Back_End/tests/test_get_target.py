import pytest
from app import main
from app.target_repository import saveTarget

URL = "https://www.google.com/maps/place/Chipotle/data=!1s0x89c2fa2bfb0d27d5:0xcceef158b20fbf10"


class FakeQuery:
    """Tiny in-memory stand-in for the Supabase query builder."""

    def __init__(self, rows):
        self.rows, self.filters, self.newRow = rows, [], None

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

    def order(self, *_, **__):
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
def targetA(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(main, "supabaseClient", fake)
    return saveTarget(fake, "user_A", "0x1:0x2", "A's Cafe", URL)


def test_owner_can_open_their_target(targetA):
    target = main.getTarget(targetA["id"], "user_A")

    assert target["business_name"] == "A's Cafe"
    assert target["platform"] == "GOOGLE_MAPS"
    assert target["source_url"] == URL


def test_another_user_is_denied_and_gets_no_data(targetA):
    with pytest.raises(main.HTTPException) as err:
        main.getTarget(targetA["id"], "user_B")

    assert err.value.status_code in (403, 404)
    assert "A's Cafe" not in str(err.value.detail)


def test_target_with_no_ingestion_is_not_started(targetA):
    assert main.getTarget(targetA["id"], "user_A")["ingestion_status"] == "not_started"
