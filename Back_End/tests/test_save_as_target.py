"""S3-003: Save As makes a separate analysis with its own copy of the stored reviews.

Rule under test: reviews are copied, Q&A history is not (the copy starts with an empty history).
"""
import copy
import itertools

import pytest
from fastapi import HTTPException
from app import main, target_copy

URL = (
    "https://www.google.com/maps/place/Chipotle+Mexican+Grill/data=!4m7!3m6"
    "!1s0x89c2fa2bfb0d27d5:0xcceef158b20fbf10!8m2"
)
PLACE = "0x89c2fa2bfb0d27d5:0xcceef158b20fbf10"


class FakeQuery:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.filters, self.changes, self.new_rows, self.deleting = [], None, None, False
        self.window, self.columns = None, None

    def select(self, columns="*"):
        self.columns = None if columns == "*" else columns.split(",")  # a real database returns only these
        return self

    def insert(self, rows):
        self.new_rows = rows if isinstance(rows, list) else [rows]
        self.single = not isinstance(rows, list)
        return self

    def update(self, values):
        self.changes = values
        return self

    def delete(self):
        self.deleting = True
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def in_(self, column, values):
        self.filters.append(lambda r: r.get(column) in values)
        return self

    def order(self, *_, **__):
        return self

    def range(self, start, end):
        self.window = (start, end)
        return self

    def execute(self):
        db = self.db
        if self.new_rows is not None:
            db.fail_on_insert and db.fail_on_insert(self.table)
            saved = [{"id": f"{self.table}-new-{next(db.counter)}", **r} for r in self.new_rows]
            db.tables[self.table].extend(saved)
            db.writes.append(("insert", self.table, len(saved)))
            return _result(saved)
        rows = [r for r in db.tables[self.table] if all(f(r) for f in self.filters)]
        if self.deleting:
            db.tables[self.table] = [r for r in db.tables[self.table] if r not in rows]
            if self.table == "analysis_targets":  # ON DELETE CASCADE
                gone = {r["id"] for r in rows}
                for child in ("reviews", "ingestion_jobs", "qa_history"):
                    db.tables[child] = [r for r in db.tables[child] if r["analysis_target_id"] not in gone]
            db.writes.append(("delete", self.table, len(rows)))
            return _result(rows)
        if self.changes is not None:
            for row in rows:
                row.update(self.changes)
            db.writes.append(("update", self.table, len(rows)))
        if self.window:
            rows = rows[self.window[0] : self.window[1] + 1]
        if self.columns:
            rows = [{c: r.get(c) for c in self.columns} for r in rows]
        return _result(rows)


def _result(rows):
    return type("Result", (), {"data": [dict(r) for r in rows]})()  # copies, like a real database


class FakeClient:
    def __init__(self):
        self.writes, self.counter, self.fail_on_insert = [], itertools.count(1), None
        self.tables = {"analysis_targets": [], "reviews": [], "ingestion_jobs": [], "qa_history": []}

    def table(self, name):
        return FakeQuery(self, name)

    def rpc(self, name, params):
        ratings = [r["rating"] for r in self.tables["reviews"] if r["analysis_target_id"] == params["target_id"]]
        average = sum(ratings) / len(ratings) if ratings else None
        rows = [{"review_count": len(ratings), "average_rating": average}]
        return type("Rpc", (), {"execute": lambda self_: _result(rows)})()


def addTarget(fake, targetId, owner, name, reviews=3, job=True):
    fake.tables["analysis_targets"].append(
        {
            "id": targetId, "owner_clerk_id": owner, "business_name": name, "platform": "GOOGLE_MAPS",
            "source_url": URL, "google_place_id": PLACE, "created_at": "2026-11-01T00:00:00Z",
            "current_ingestion_id": f"job-{targetId}" if job else None,
            "current_ingestion_at": "2026-11-02T10:00:00Z" if job else None,
        }
    )
    for n in range(reviews):
        fake.tables["reviews"].append(
            {
                "id": f"{targetId}-r{n}", "analysis_target_id": targetId, "google_review_id": f"g-{targetId}-{n}",
                "rating": 5 - n, "review_text": f"Review {n}", "reviewed_at": f"2026-10-0{n + 1}T00:00:00Z",
                "ingested_at": "2026-11-02T10:00:00Z",
            }
        )
    if job:
        fake.tables["ingestion_jobs"].append(
            {
                "id": f"job-{targetId}", "analysis_target_id": targetId, "status": "completed",
                "reviews_ingested": reviews, "reviews_skipped": 2, "created_at": "2026-11-02T09:59:00Z",
                "started_at": "2026-11-02T09:59:30Z", "completed_at": "2026-11-02T10:00:00Z",
            }
        )
    fake.tables["qa_history"].append({"id": f"qa-{targetId}", "analysis_target_id": targetId, "question": "Q", "answer": "A"})


@pytest.fixture
def db(monkeypatch):
    """user_A owns target-A (3 reviews) and target-E (no reviews yet). user_B owns target-C."""
    fake = FakeClient()
    addTarget(fake, "target-A", "user_A", "Downtown lunch")
    addTarget(fake, "target-C", "user_B", "Elsewhere")
    addTarget(fake, "target-E", "user_A", "Not loaded yet", reviews=0, job=False)
    fake.writes.clear()
    monkeypatch.setattr(main, "supabaseClient", fake)
    return fake


def saveAs(targetId, name, user="user_A"):
    return main.saveTargetAs(targetId, main.TargetSaveAsRequest(name=name), user)


def rows(db, table, targetId):
    return [r for r in db.tables[table] if r["analysis_target_id"] == targetId]


def target(db, targetId):
    return next(t for t in db.tables["analysis_targets"] if t["id"] == targetId)


# ---- a new analysis is made -----------------------------------------------------


def test_save_as_creates_a_new_analysis_with_the_new_name(db):
    result = saveAs("target-A", "Downtown lunch (copy)")

    assert result["id"] != "target-A"
    assert result["business_name"] == "Downtown lunch (copy)"
    assert len([t for t in db.tables["analysis_targets"] if t["owner_clerk_id"] == "user_A"]) == 3


def test_the_copy_keeps_the_source_link_place_and_platform(db):
    result = saveAs("target-A", "Copy")

    assert (result["source_url"], result["google_place_id"], result["platform"]) == (URL, PLACE, "GOOGLE_MAPS")


def test_the_copy_belongs_to_the_user_who_made_it(db):
    assert saveAs("target-A", "Copy")["owner_clerk_id"] == "user_A"


def test_the_new_name_is_cleaned_like_any_analysis_name(db):
    assert saveAs("target-A", "  My   copy ")["business_name"] == "My copy"


def test_the_original_keeps_its_name_and_its_other_details(db):
    before = copy.deepcopy(target(db, "target-A"))

    saveAs("target-A", "Copy")

    assert target(db, "target-A") == before


# ---- the review dataset is copied ------------------------------------------------


def test_the_copy_has_the_same_reviews(db):
    result = saveAs("target-A", "Copy")

    original = [(r["google_review_id"], r["rating"], r["review_text"], r["reviewed_at"]) for r in rows(db, "reviews", "target-A")]
    copied = [(r["google_review_id"], r["rating"], r["review_text"], r["reviewed_at"]) for r in rows(db, "reviews", result["id"])]
    assert copied == original and len(copied) == 3


def test_the_copy_has_its_own_review_rows_not_shared_ones(db):
    result = saveAs("target-A", "Copy")

    original_ids = {r["id"] for r in rows(db, "reviews", "target-A")}
    copied_ids = {r["id"] for r in rows(db, "reviews", result["id"])}
    assert not original_ids & copied_ids


def test_the_original_reviews_are_unchanged(db):
    before = copy.deepcopy(rows(db, "reviews", "target-A"))

    saveAs("target-A", "Copy")

    assert rows(db, "reviews", "target-A") == before


def test_the_summary_returned_matches_the_copied_reviews(db):
    result = saveAs("target-A", "Copy")

    assert result["review_summary"]["review_count"] == 3


def test_a_large_dataset_is_copied_in_full(db, monkeypatch):
    monkeypatch.setattr(target_copy, "PAGE_SIZE", 4)
    monkeypatch.setattr(target_copy, "INSERT_BATCH", 3)
    for n in range(3, 11):
        db.tables["reviews"].append(
            {"id": f"target-A-r{n}", "analysis_target_id": "target-A", "google_review_id": f"g-target-A-{n}", "rating": 4,
             "review_text": f"Review {n}", "reviewed_at": None, "ingested_at": "2026-11-02T10:00:00Z"}
        )

    result = saveAs("target-A", "Copy")

    assert len(rows(db, "reviews", result["id"])) == 11


# ---- ingestion state --------------------------------------------------------------


def test_the_copy_shows_the_same_ingestion_state_as_the_original(db):
    result = saveAs("target-A", "Copy")

    assert result["ingestion_status"] == main.getTarget("target-A", "user_A")["ingestion_status"] == "partial"
    assert result["ingestion_skipped"] == 2


def test_the_copy_has_its_own_ingestion_record(db):
    result = saveAs("target-A", "Copy")

    jobs = rows(db, "ingestion_jobs", result["id"])
    assert len(jobs) == 1 and jobs[0]["id"] != "job-target-A"
    assert jobs[0]["reviews_ingested"] == 3
    assert result["current_ingestion_id"] == jobs[0]["id"]
    assert result["current_ingestion_at"] == "2026-11-02T10:00:00Z"


def test_the_original_ingestion_record_is_unchanged(db):
    before = copy.deepcopy(rows(db, "ingestion_jobs", "target-A"))

    saveAs("target-A", "Copy")

    assert rows(db, "ingestion_jobs", "target-A") == before
    assert target(db, "target-A")["current_ingestion_id"] == "job-target-A"


def test_saving_an_analysis_with_no_reviews_yet_gives_an_empty_copy(db):
    result = saveAs("target-E", "Empty copy")

    assert rows(db, "reviews", result["id"]) == []
    assert result["ingestion_status"] == "not_started"
    assert result["review_summary"]["review_count"] == 0


# ---- Q&A history is not copied -----------------------------------------------------


def test_the_copy_starts_with_an_empty_qa_history(db):
    result = saveAs("target-A", "Copy")

    assert rows(db, "qa_history", result["id"]) == []


def test_the_original_qa_history_is_untouched(db):
    saveAs("target-A", "Copy")

    assert len(rows(db, "qa_history", "target-A")) == 1


# ---- the copy and the original stay apart -------------------------------------------


def test_renaming_the_copy_does_not_rename_the_original(db):
    result = saveAs("target-A", "Copy")

    main.renameTarget(result["id"], main.TargetRenameRequest(name="Renamed copy"), "user_A")

    assert target(db, "target-A")["business_name"] == "Downtown lunch"
    assert target(db, result["id"])["business_name"] == "Renamed copy"


def test_deleting_the_copy_does_not_delete_the_original(db):
    result = saveAs("target-A", "Copy")

    db.table("analysis_targets").delete().eq("id", result["id"]).execute()

    assert target(db, "target-A")["business_name"] == "Downtown lunch"
    assert len(rows(db, "reviews", "target-A")) == 3
    assert len(rows(db, "ingestion_jobs", "target-A")) == 1
    assert len(rows(db, "qa_history", "target-A")) == 1
    assert rows(db, "reviews", result["id"]) == []


def test_changing_the_copys_reviews_does_not_change_the_original(db):
    """What a refresh does to the copy: its review rows are replaced. The original's are not."""
    result = saveAs("target-A", "Copy")
    before = copy.deepcopy(rows(db, "reviews", "target-A"))

    db.table("reviews").delete().eq("analysis_target_id", result["id"]).execute()
    db.table("reviews").insert({"analysis_target_id": result["id"], "rating": 1, "review_text": "New"}).execute()

    assert rows(db, "reviews", "target-A") == before


def test_saving_twice_gives_two_separate_copies(db):
    first = saveAs("target-A", "Copy")
    second = saveAs("target-A", "Copy")

    assert first["id"] != second["id"]
    assert len(rows(db, "reviews", first["id"])) == len(rows(db, "reviews", second["id"])) == 3


def test_saving_a_copy_of_a_copy_works(db):
    first = saveAs("target-A", "Copy")

    second = saveAs(first["id"], "Copy of copy")

    assert len(rows(db, "reviews", second["id"])) == 3
    assert second["ingestion_status"] == "partial"


# ---- only the owner, only a valid name ------------------------------------------------


def test_another_users_analysis_cannot_be_copied(db):
    with pytest.raises(HTTPException) as error:
        saveAs("target-C", "Stolen", user="user_A")

    assert error.value.status_code == 403
    assert db.writes == []


def test_a_missing_analysis_is_a_404(db):
    with pytest.raises(HTTPException) as error:
        saveAs("nope", "Copy")

    assert error.value.status_code == 404
    assert db.writes == []


@pytest.mark.parametrize("name", ["", "   ", "!!!", "x" * 500, "bad\x00name"])
def test_a_bad_name_is_rejected_and_nothing_is_created(db, name):
    with pytest.raises(HTTPException) as error:
        saveAs("target-A", name)

    assert error.value.status_code == 422
    assert error.value.detail[0]["loc"] == ["body", "name"]
    assert db.writes == []


def test_another_user_gets_403_even_with_a_bad_name(db):
    with pytest.raises(HTTPException) as error:
        saveAs("target-C", "", user="user_A")

    assert error.value.status_code == 403


# ---- a failure leaves nothing behind ----------------------------------------------------


def test_if_copying_reviews_fails_the_half_made_copy_is_removed(db):
    def boom(table):
        if table == "reviews":
            raise RuntimeError("database went away")

    db.fail_on_insert = boom

    with pytest.raises(HTTPException) as error:
        saveAs("target-A", "Copy")

    assert error.value.status_code == 503
    assert [t["id"] for t in db.tables["analysis_targets"]] == ["target-A", "target-C", "target-E"]
    assert len(rows(db, "reviews", "target-A")) == 3


def test_if_the_ingestion_record_fails_nothing_is_left_behind(db):
    def boom(table):
        if table == "ingestion_jobs":
            raise RuntimeError("database went away")

    db.fail_on_insert = boom

    with pytest.raises(HTTPException):
        saveAs("target-A", "Copy")

    assert [t["id"] for t in db.tables["analysis_targets"]] == ["target-A", "target-C", "target-E"]
    assert len(db.tables["reviews"]) == 3 + 3  # target-A and target-C only


def test_the_error_message_does_not_leak_database_details(db):
    def boom(table):
        raise RuntimeError("secret connection string")

    db.fail_on_insert = boom

    with pytest.raises(HTTPException) as error:
        saveAs("target-A", "Copy")

    assert "secret" not in str(error.value.detail)
