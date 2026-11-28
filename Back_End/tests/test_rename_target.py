"""S3-002: rename an analysis. Only the name changes, and only the owner can do it."""
import copy

import pytest
from app import main

URL = (
    "https://www.google.com/maps/place/Chipotle+Mexican+Grill/data=!4m7!3m6"
    "!1s0x89c2fa2bfb0d27d5:0xcceef158b20fbf10!8m2"
)


class FakeQuery:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.changes = db, table, [], None

    def select(self, *_):
        return self

    def update(self, values):
        self.changes = values
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
        rows = [r for r in self.db.tables[self.table] if all(f(r) for f in self.filters)]
        if self.changes is not None:
            self.db.writes.append((self.table, dict(self.changes)))
            for row in rows:
                row.update(self.changes)
        return type("Result", (), {"data": [dict(r) for r in rows]})()  # copies, like a real database


class FakeClient:
    def __init__(self):
        self.writes = []
        self.tables = {"analysis_targets": [], "reviews": [], "ingestion_jobs": [], "qa_history": []}

    def table(self, name):
        return FakeQuery(self, name)

    def rpc(self, name, params):
        ratings = [r["rating"] for r in self.tables["reviews"] if r["analysis_target_id"] == params["target_id"]]
        average = sum(ratings) / len(ratings) if ratings else None
        return FakeQuery(_Rows([{"review_count": len(ratings), "average_rating": average}]), "rows")


class _Rows:
    """Lets rpc() reuse FakeQuery for a fixed list of rows."""

    def __init__(self, rows):
        self.tables, self.writes = {"rows": rows}, []


@pytest.fixture
def db(monkeypatch):
    """user_A owns target-A and target-B. user_B owns target-C."""
    fake = FakeClient()
    for targetId, owner, name in (("target-A", "user_A", "Downtown lunch"), ("target-B", "user_A", "Airport kiosk"), ("target-C", "user_B", "Elsewhere")):
        fake.tables["analysis_targets"].append(
            {
                "id": targetId, "owner_clerk_id": owner, "business_name": name, "platform": "GOOGLE_MAPS",
                "source_url": URL, "google_place_id": "0x89c2fa2bfb0d27d5:0xcceef158b20fbf10",
                "current_ingestion_id": f"job-{targetId}", "current_ingestion_at": "2026-11-01T00:00:00Z",
                "created_at": "2026-11-01T00:00:00Z",
            }
        )
        fake.tables["reviews"].append({"id": f"{targetId}-r1", "analysis_target_id": targetId, "review_text": "Great", "rating": 5})
        fake.tables["ingestion_jobs"].append(
            {"id": f"job-{targetId}", "analysis_target_id": targetId, "status": "completed", "created_at": "2026-11-01T00:00:00Z"}
        )
        fake.tables["qa_history"].append({"id": f"qa-{targetId}", "analysis_target_id": targetId, "question": "Q", "answer": "A"})
    monkeypatch.setattr(main, "supabaseClient", fake)
    return fake


def rename(targetId, name, user="user_A"):
    return main.renameTarget(targetId, main.TargetRenameRequest(name=name), user)


def row(db, targetId):
    return next(t for t in db.tables["analysis_targets"] if t["id"] == targetId)


# ---- the owner renames --------------------------------------------------------


def test_owner_can_rename_and_gets_the_updated_analysis_back(db):
    result = rename("target-A", "Lunch spot downtown")

    assert result["business_name"] == "Lunch spot downtown"
    assert row(db, "target-A")["business_name"] == "Lunch spot downtown"


def test_the_new_name_is_cleaned_like_a_new_analysis_name(db):
    assert rename("target-A", "  Lunch    spot  ")["business_name"] == "Lunch spot"


def test_the_new_name_is_what_opening_the_analysis_shows_afterwards(db):
    rename("target-A", "Lunch spot downtown")

    assert main.getTarget("target-A", "user_A")["business_name"] == "Lunch spot downtown"


def test_renaming_to_the_same_name_is_fine(db):
    assert rename("target-A", "Downtown lunch")["business_name"] == "Downtown lunch"


def test_two_analyses_may_end_up_with_the_same_name(db):
    rename("target-B", "Downtown lunch")

    assert row(db, "target-A")["business_name"] == row(db, "target-B")["business_name"] == "Downtown lunch"


def test_renaming_one_analysis_does_not_rename_the_others(db):
    rename("target-A", "Lunch spot downtown")

    assert row(db, "target-B")["business_name"] == "Airport kiosk"
    assert row(db, "target-C")["business_name"] == "Elsewhere"


# ---- only the name changes ------------------------------------------------------


def test_only_the_name_is_written_and_nothing_else_changes(db):
    before = copy.deepcopy(db.tables)

    rename("target-A", "Lunch spot downtown")

    assert db.writes == [("analysis_targets", {"business_name": "Lunch spot downtown"})]
    after = copy.deepcopy(db.tables)
    before["analysis_targets"][0]["business_name"] = "Lunch spot downtown"
    assert after == before  # source, dataset link, reviews, ingestion history and Q&A are untouched


def test_source_dataset_and_history_are_still_there_after_a_rename(db):
    rename("target-A", "Lunch spot downtown")
    target = main.getTarget("target-A", "user_A")

    assert target["source_url"] == URL
    assert target["current_ingestion_id"] == "job-target-A"
    assert target["review_summary"]["review_count"] == 1
    assert [q["id"] for q in db.tables["qa_history"] if q["analysis_target_id"] == "target-A"] == ["qa-target-A"]


# ---- unusable names ---------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "   ", "---", "x" * 121, "bad\x00name"])
def test_an_unusable_name_is_rejected_and_the_old_name_stays(db, bad):
    with pytest.raises(main.HTTPException) as err:
        rename("target-A", bad)

    assert err.value.status_code == 422
    assert [e["loc"][1] for e in err.value.detail] == ["name"]
    assert row(db, "target-A")["business_name"] == "Downtown lunch"
    assert db.writes == []


# ---- who may rename --------------------------------------------------------------


def test_another_user_cannot_rename_the_analysis(db):
    with pytest.raises(main.HTTPException) as err:
        rename("target-A", "Hijacked", user="user_B")

    assert err.value.status_code in (403, 404)
    assert row(db, "target-A")["business_name"] == "Downtown lunch"
    assert db.writes == []


def test_another_user_gets_the_same_answer_for_a_good_or_a_bad_name(db):
    """The owner check comes first, so a stranger cannot use rename to learn anything."""
    codes = []
    for name in ("Hijacked", "---"):
        with pytest.raises(main.HTTPException) as err:
            rename("target-A", name, user="user_B")
        codes.append(err.value.status_code)

    assert codes[0] == codes[1]


def test_a_missing_analysis_cannot_be_renamed(db):
    with pytest.raises(main.HTTPException) as err:
        rename("no-such-target", "Anything")

    assert err.value.status_code == 404
    assert db.writes == []


def test_the_write_itself_is_limited_to_the_owner(db):
    """Even if the earlier check were skipped, updateTargetName only matches the owner's row."""
    from app.target_rename import updateTargetName

    assert updateTargetName(db, "target-A", "user_B", "Hijacked") is None
    assert row(db, "target-A")["business_name"] == "Downtown lunch"
