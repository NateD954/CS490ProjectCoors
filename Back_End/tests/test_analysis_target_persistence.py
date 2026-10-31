from app.target_repository import saveTarget, getTargetForOwner


class FakeQuery:
    """Minimal in-memory stand-in for the Supabase query builder."""

    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.newRow = None

    def insert(self, row):
        self.newRow = row
        return self

    def select(self, *_):
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

        matches = [r for r in self.rows if all(r.get(c) == v for c, v in self.filters)]

        class Result:
            data = matches

        return Result()


class FakeClient:
    def __init__(self):
        self.rows = []

    def table(self, _name):
        return FakeQuery(self.rows)


URL = "https://www.google.com/maps/place/Joes+Pizza"


def test_saved_target_can_be_retrieved_with_expected_values():
    client = FakeClient()
    saved = saveTarget(client, "user_A", "ChIJabc123", "Joe's Pizza", URL)

    found = getTargetForOwner(client, saved["id"], "user_A")

    assert found["owner_clerk_id"] == "user_A"
    assert found["business_name"] == "Joe's Pizza"
    assert found["google_place_id"] == "ChIJabc123"
    assert found["platform"] == "GOOGLE_MAPS"
    assert found["source_url"] == URL
    assert found["created_at"] is not None


def test_target_is_not_returned_for_a_different_owner():
    client = FakeClient()
    saved = saveTarget(client, "user_A", "ChIJabc123", "Joe's Pizza", URL)

    assert getTargetForOwner(client, saved["id"], "user_B") is None


def test_unknown_target_returns_none():
    assert getTargetForOwner(FakeClient(), "does-not-exist", "user_A") is None


def test_targets_are_kept_separate_per_owner():
    client = FakeClient()
    a = saveTarget(client, "user_A", "ChIJaaa", "A's Place", URL)
    b = saveTarget(client, "user_B", "ChIJbbb", "B's Place", URL)

    assert getTargetForOwner(client, a["id"], "user_A")["business_name"] == "A's Place"
    assert getTargetForOwner(client, b["id"], "user_B")["business_name"] == "B's Place"
    assert getTargetForOwner(client, a["id"], "user_B") is None
