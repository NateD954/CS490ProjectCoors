import pytest
from app import main

DATA_ID = "0x89c2fa2bfb0d27d5:0xcceef158b20fbf10"
GOOD_URL = f"https://www.google.com/maps/place/Chipotle/data=!4m7!3m6!1s{DATA_ID}!8m2"


class FakeQuery:
    def __init__(self, rows):
        self.rows, self.row = rows, None

    def insert(self, row):
        self.row = {"id": "target-1", "created_at": "2026-11-02T00:00:00Z", **row}
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
        return FakeQuery(self.targets)


@pytest.fixture
def client(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(main, "supabaseClient", fake)
    return fake


def create(name="Chipotle", sourceUrl=GOOD_URL, platform="GOOGLE_MAPS"):
    body = main.TargetCreateRequest(name=name, platform=platform, sourceUrl=sourceUrl)
    return main.createTarget(body, "user_A")


def rejectedFields(**kwargs):
    with pytest.raises(main.HTTPException) as err:
        create(**kwargs)
    assert err.value.status_code == 422
    return [e["loc"][1] for e in err.value.detail]


def test_valid_input_is_accepted(client):
    assert create()["business_name"] == "Chipotle"
    assert len(client.targets) == 1


def test_missing_name_is_rejected(client):
    assert "name" in rejectedFields(name="")
    assert client.targets == []


def test_missing_source_is_rejected(client):
    assert "sourceUrl" in rejectedFields(sourceUrl="")
    assert client.targets == []


@pytest.mark.parametrize("bad", ["not a url", "ftp://www.google.com/maps/" + DATA_ID, "javascript:alert(1)"])
def test_malformed_source_is_rejected(client, bad):
    assert "sourceUrl" in rejectedFields(sourceUrl=bad)
    assert client.targets == []


@pytest.mark.parametrize(
    "bad",
    [
        f"https://evil.com/?x={DATA_ID}",
        f"https://www.amazon.com/dp/B000/{DATA_ID}",
        f"https://google.com.evil.com/maps/{DATA_ID}",
        f"https://notgoogle.com/maps/{DATA_ID}",
    ],
)
def test_link_from_another_site_is_rejected_even_with_a_place_id(client, bad):
    assert "sourceUrl" in rejectedFields(sourceUrl=bad)
    assert client.targets == []


def test_google_link_without_a_place_id_is_rejected(client):
    assert "sourceUrl" in rejectedFields(sourceUrl="https://www.google.com/maps/place/Chipotle")
    assert client.targets == []


def test_messages_are_readable_for_the_user(client):
    with pytest.raises(main.HTTPException) as err:
        create(name="", sourceUrl="nope")
    messages = [e["msg"] for e in err.value.detail]
    assert all(m and "Traceback" not in m for m in messages)
    assert len(messages) == 2
