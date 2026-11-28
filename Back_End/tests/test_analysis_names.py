"""S3-001: the name of a saved analysis."""
import pytest
from app import main
from app.analysis_names import MAX_NAME_LENGTH, cleanName

URL = (
    "https://www.google.com/maps/place/Chipotle+Mexican+Grill/data=!4m7!3m6"
    "!1s0x89c2fa2bfb0d27d5:0xcceef158b20fbf10!8m2"
)
PLACE_ID = "0x89c2fa2bfb0d27d5:0xcceef158b20fbf10"


# ---- the name rules ----------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Chipotle", "Chipotle"),
        ("  Chipotle  ", "Chipotle"),
        ("Downtown   lunch\tspot", "Downtown lunch spot"),
        ("Line one\nline two", "Line one line two"),
        ("Café Münch 2", "Café Münch 2"),
        ("7", "7"),
        ("a" * MAX_NAME_LENGTH, "a" * MAX_NAME_LENGTH),
    ],
)
def test_usable_names_are_cleaned_and_accepted(raw, expected):
    assert cleanName(raw) == (expected, None)


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "\n\t", "---", "???", "!!! ...", "a" * (MAX_NAME_LENGTH + 1), "bad\x00name", "bell\x07", None, 42],
)
def test_unusable_names_are_rejected_with_a_message(raw):
    _, problem = cleanName(raw)

    assert problem


def test_a_name_made_longer_only_by_extra_spaces_is_still_accepted():
    name = "Chipotle" + " " * 500 + "Downtown"

    assert cleanName(name) == ("Chipotle Downtown", None)


# ---- saving an analysis through the create endpoint --------------------------


class FakeQuery:
    def __init__(self, rows):
        self.rows, self.row = rows, None

    def insert(self, row):
        self.row = {"id": f"target-{len(self.rows) + 1}", "created_at": "2026-11-02T00:00:00Z", **row}
        return self

    def execute(self):
        self.rows.append(self.row)
        return type("Result", (), {"data": [self.row]})()


class FakeClient:
    def __init__(self):
        self.targets = []

    def table(self, name):
        assert name == "analysis_targets"
        return FakeQuery(self.targets)


@pytest.fixture
def client(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(main, "supabaseClient", fake)
    return fake


def create(name, user="user_A"):
    return main.createTarget(main.TargetCreateRequest(name=name, platform="GOOGLE_MAPS", sourceUrl=URL), user)


def test_the_name_is_independent_of_the_source_url(client):
    saved = create("Downtown lunch spot")

    assert saved["business_name"] == "Downtown lunch spot"
    assert "Chipotle" in saved["source_url"]  # the URL still names the place, the saved name does not


def test_the_saved_record_keeps_name_owner_source_and_identity(client):
    saved = create("Downtown lunch spot", user="user_A")

    assert saved["business_name"] == "Downtown lunch spot"
    assert saved["owner_clerk_id"] == "user_A"
    assert saved["source_url"] == URL
    assert saved["google_place_id"] == PLACE_ID
    assert saved["id"]  # the target's own identity
    assert "current_ingestion_id" not in saved or saved["current_ingestion_id"] is None  # no dataset yet


def test_extra_spaces_inside_the_name_are_tidied_before_saving(client):
    assert create("  Downtown    lunch   spot ")["business_name"] == "Downtown lunch spot"


def test_two_analyses_may_share_a_name(client):
    create("Lunch spot")
    create("Lunch spot")

    assert [t["business_name"] for t in client.targets] == ["Lunch spot", "Lunch spot"]


@pytest.mark.parametrize("bad", ["", "   ", "---", "x" * (MAX_NAME_LENGTH + 1)])
def test_an_unusable_name_is_rejected_and_nothing_is_saved(client, bad):
    with pytest.raises(main.HTTPException) as err:
        create(bad)

    assert err.value.status_code == 422
    assert [e["loc"][1] for e in err.value.detail] == ["name"]
    assert client.targets == []
