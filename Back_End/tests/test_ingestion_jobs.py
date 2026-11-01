from app.target_repository import createIngestionJob, markIngestionRunning, markIngestionCompleted, markIngestionFailed

class FakeQuery:
    """Minimal in-memory stand-in for the Supabase query builder."""

    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.newRow = None
        self.updatedRow = None

    def insert(self, row):
        self.newRow = row
        return self

    def select(self, *_):
        return self

    def update(self, row):
        self.updatedRow = row
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def execute(self):
        if self.newRow is not None:
            saved = {
                "id": f"id-{len(self.rows) + 1}",
                "created_at": "2026-10-31T12:00:00Z",
                **self.newRow,
            }
            self.rows.append(saved)

            class Result:
                data = [saved]

            return Result()

        if self.updatedRow is not None:
            matches = [r for r in self.rows if all(r.get(c) == v for c, v in self.filters)]

            for row in matches:
                row.update(self.updatedRow)

            class Result:
                data = matches

            return Result()

        matches = [r for r in self.rows if all(r.get(c) == v for c, v in self.filters)]

        class Result:
            data = matches

        return Result()


class FakeClient:
    def __init__(self):
        self.tables = {
            "analysis_targets": [],
            "reviews": [],
            "ingestion_jobs": []
        }

    def table(self, name):
        return FakeQuery(self.tables[name])

# test 1
# does the ingestion job instantiate with the correct default values?
def test_ingestion_job_starts_pending():
    client = FakeClient()

    job = createIngestionJob(client, "target-1")

    assert job["analysis_target_id"] == "target-1"
    assert job["status"] == "pending"
    assert job["reviews_ingested"] == 0
    assert job["error_message"] is None

# test 2
# if we mark a job as running, will it be properly marked?
def test_ingestion_job_can_be_marked_running():
    client = FakeClient()

    job = createIngestionJob(client, "target-1")
    updated = markIngestionRunning(client, job["id"])

    assert updated["status"] == "running"

# test 3
# if we mark a job as completed, will it be properly marked?
def test_ingestion_job_can_be_completed():
    client = FakeClient()

    job = createIngestionJob(client, "target-1")
    updated = markIngestionCompleted(client, job["id"], 12)

    assert updated["status"] == "completed"
    assert updated["reviews_ingested"] == 12
    assert updated["error_message"] is None

# test 4
# again, if we mark a job as failed, will it be properly marked?
def test_ingestion_job_can_fail():
    client = FakeClient()

    job = createIngestionJob(client, "target-1")
    updated = markIngestionFailed(client, job["id"], "SerpAPI failed")

    assert updated["status"] == "failed"
    assert updated["error_message"] == "SerpAPI failed"