"""S2-018: after switching targets, questions use the new target's reviews only.

Target A's reviews all talk about "battery life". Target B's all talk about
"customer service". Both belong to the same user, so only the target changes.
"""
import pytest
from app import main

URL = "https://www.google.com/maps/place/Chipotle/data=!1s0x89c2fa2bfb0d27d5:0xcceef158b20fbf10"

A_REVIEWS = [("Battery life is great", 5), ("Battery life lasts days", 5), ("Battery life could be better", 4)]
B_REVIEWS = [("Customer service was kind", 4), ("Customer service fixed it fast", 2)]


class FakeQuery:
    def __init__(self, rows):
        self.rows, self.filters = rows, []

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
        return type("Result", (), {"data": [r for r in self.rows if all(f(r) for f in self.filters)]})()


class FakeClient:
    def __init__(self):
        self.tables = {"analysis_targets": [], "reviews": [], "ingestion_jobs": []}

    def table(self, name):
        return FakeQuery(self.tables[name])

    def rpc(self, name, params):
        """Works out the summary from the stored reviews, like the real database function."""
        assert name == "get_target_review_summary"
        ratings = [r["rating"] for r in self.tables["reviews"] if r["analysis_target_id"] == params["target_id"]]
        average = sum(ratings) / len(ratings) if ratings else None
        return FakeQuery([{"review_count": len(ratings), "average_rating": average}])


class FakeProviderResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}


@pytest.fixture
def db(monkeypatch):
    fake = FakeClient()
    for targetId, name, reviews in (("target-A", "A's Gadgets", A_REVIEWS), ("target-B", "B's Repair Shop", B_REVIEWS)):
        fake.tables["analysis_targets"].append(
            {"id": targetId, "owner_clerk_id": "user_A", "business_name": name, "platform": "GOOGLE_MAPS", "source_url": URL}
        )
        for i, (text, rating) in enumerate(reviews):
            fake.tables["reviews"].append(
                {"id": f"{targetId}-r{i}", "analysis_target_id": targetId, "review_text": text, "rating": rating}
            )
    monkeypatch.setattr(main, "supabaseClient", fake)
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")
    return fake


@pytest.fixture
def providerCalls(monkeypatch):
    calls = []

    def fakePost(url, **kwargs):
        calls.append(kwargs["json"])
        return FakeProviderResponse()

    monkeypatch.setattr(main.requests, "post", fakePost)
    return calls


def ask(targetId):
    main.ask_review_question(targetId, main.QuestionRequest(question="What do people say?"), "user_A")


def evidence(call):
    return call["contents"][0]["parts"][0]["text"]


def systemPrompt(call):
    return call["systemInstruction"]["parts"][0]["text"]


def test_after_switching_from_A_to_B_the_context_has_only_B_reviews(db, providerCalls):
    ask("target-A")
    ask("target-B")

    first, second = providerCalls
    assert "Battery life" in evidence(first)
    assert "Customer service" not in evidence(first)
    assert "Customer service" in evidence(second)
    assert "Battery life" not in evidence(second)


def test_after_switching_the_instructions_name_the_new_target_only(db, providerCalls):
    ask("target-A")
    ask("target-B")

    _, second = providerCalls
    assert "B's Repair Shop" in systemPrompt(second)
    assert "A's Gadgets" not in systemPrompt(second)


def test_switching_back_and_forth_never_mixes_the_datasets(db, providerCalls):
    for targetId in ("target-A", "target-B", "target-A", "target-B"):
        ask(targetId)

    texts = [evidence(c) for c in providerCalls]
    assert texts[0] == texts[2]  # A's context is identical every time
    assert texts[1] == texts[3]  # B's context is identical every time
    assert "Customer service" not in texts[2]
    assert "Battery life" not in texts[3]


def test_every_review_sent_belongs_to_the_active_target(db, providerCalls):
    ask("target-B")

    sent = evidence(providerCalls[0])
    for text, _ in B_REVIEWS:
        assert f"- {text}" in sent
    for text, _ in A_REVIEWS:
        assert text not in sent


def test_summary_follows_the_active_target(db):
    summaryA = main.getTarget("target-A", "user_A")["review_summary"]
    summaryB = main.getTarget("target-B", "user_A")["review_summary"]

    assert summaryA["review_count"] == 3
    assert summaryB["review_count"] == 2
    assert summaryB["average_rating"] == 3  # (4 + 2) / 2, not A's average
