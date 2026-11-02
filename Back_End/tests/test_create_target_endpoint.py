import pytest
from app import main

URL = (
    "https://www.google.com/maps/place/Chipotle+Mexican+Grill/data=!4m7!3m6"
    "!1s0x89c2fa2bfb0d27d5:0xcceef158b20fbf10!8m2"
)


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.row = None

    def insert(self, row):
        self.row = {"id": f"target-{len(self.rows) + 1}", "created_at": "2026-11-02T00:00:00Z", **row}
        return self

    def execute(self):
        self.rows.append(self.row)

        class Result:
            data = [self.row]

        return Result()


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


def request(**overrides):
    body = {"name": "Chipotle", "platform": "GOOGLE_MAPS", "sourceUrl": URL}
    body.update(overrides)
    return main.TargetCreateRequest(**body)


def test_valid_target_is_saved_for_the_logged_in_user(client):
    saved = main.createTarget(request(), "user_A")

    assert saved["owner_clerk_id"] == "user_A"
    assert saved["business_name"] == "Chipotle"
    assert saved["platform"] == "GOOGLE_MAPS"
    assert saved["source_url"] == URL
    assert saved["google_place_id"] == "0x89c2fa2bfb0d27d5:0xcceef158b20fbf10"
    assert len(client.targets) == 1


def test_owner_sent_by_the_client_is_ignored(client):
    # Extra fields such as userId / owner_clerk_id are not part of the request model.
    body = main.TargetCreateRequest(
        name="Chipotle", platform="GOOGLE_MAPS", sourceUrl=URL, userId="user_B", owner_clerk_id="user_B"
    )
    saved = main.createTarget(body, "user_A")

    assert saved["owner_clerk_id"] == "user_A"
    assert not hasattr(body, "userId")


def test_name_is_trimmed_before_saving(client):
    saved = main.createTarget(request(name="  Chipotle  "), "user_A")

    assert saved["business_name"] == "Chipotle"


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"name": "   "}, "name"),
        ({"sourceUrl": ""}, "sourceUrl"),
        ({"sourceUrl": "not a url"}, "sourceUrl"),
        ({"sourceUrl": "https://www.google.com/maps/place/Chipotle"}, "sourceUrl"),
        ({"platform": "AMAZON"}, "platform"),
    ],
)
def test_invalid_target_is_rejected_and_not_saved(client, overrides, field):
    with pytest.raises(main.HTTPException) as err:
        main.createTarget(request(**overrides), "user_A")

    assert err.value.status_code == 422
    assert field in [e["loc"][1] for e in err.value.detail]
    assert client.targets == []
