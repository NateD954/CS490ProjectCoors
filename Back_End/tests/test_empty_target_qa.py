"""S2-020: a target with no usable review data must never reach the AI provider."""
import pytest
from app import main

URL = "https://www.google.com/maps/place/Chipotle/data=!1s0x89c2fa2bfb0d27d5:0xcceef158b20fbf10"


class FakeQuery:
    def __init__(self, rows):
        self.rows, self.filters = rows, []

    def select(self, *_):
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def execute(self):
        return type("Result", (), {"data": [r for r in self.rows if all(f(r) for f in self.filters)]})()


class FakeClient:
    def __init__(self):
        self.tables = {"analysis_targets": [], "reviews": [], "ingestion_jobs": []}

    def table(self, name):
        return FakeQuery(self.tables[name])


@pytest.fixture
def client(monkeypatch):
    """Target A (no reviews yet) and target B (has reviews), both owned by user_A."""
    fake = FakeClient()
    for targetId, name in (("target-A", "A's Cafe"), ("target-B", "B's Pizza")):
        fake.tables["analysis_targets"].append(
            {"id": targetId, "owner_clerk_id": "user_A", "business_name": name, "platform": "GOOGLE_MAPS", "source_url": URL}
        )
    monkeypatch.setattr(main, "supabaseClient", fake)
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")
    return fake


@pytest.fixture
def providerCalls(monkeypatch):
    calls = []

    def fakePost(url, **kwargs):
        calls.append(url)
        raise AssertionError("The AI provider must not be called for a target with no review data")

    monkeypatch.setattr(main.requests, "post", fakePost)
    return calls


def ask(targetId="target-A"):
    return main.ask_review_question(targetId, main.QuestionRequest(question="What do people like?"), "user_A")


def test_never_ingested_target_does_not_call_the_provider(client, providerCalls):
    result = ask()

    assert "No reviews have been ingested" in result["answer"]
    assert providerCalls == []


def test_target_whose_ingestion_failed_and_stored_nothing_does_not_call_the_provider(client, providerCalls):
    client.tables["ingestion_jobs"].append(
        {"id": "j1", "analysis_target_id": "target-A", "status": "failed", "error_message": "Provider down"}
    )

    result = ask()

    assert "No reviews have been ingested" in result["answer"]
    assert providerCalls == []


def test_reviews_that_belong_to_another_target_do_not_count_as_this_targets_data(client, providerCalls):
    client.tables["reviews"].append({"id": "r1", "analysis_target_id": "target-B", "review_text": "Great pizza"})

    result = ask("target-A")

    assert "No reviews have been ingested" in result["answer"]
    assert "Great pizza" not in result["answer"]
    assert providerCalls == []


def test_empty_target_answer_is_a_notice_not_a_general_knowledge_answer(client, providerCalls):
    result = ask()

    assert list(result) == ["answer"]
    assert "ingest" in result["answer"].lower()
