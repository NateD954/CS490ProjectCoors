"""S2-019: a new question never reuses reviews, questions or answers from an earlier request.

The backend keeps no cache or conversation memory: every question reads the target's reviews
fresh. These tests lock that in, so a future cache has to respect target and user boundaries.
"""
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
        self.tables = {"analysis_targets": [], "reviews": []}

    def table(self, name):
        return FakeQuery(self.tables[name])


class FakeProviderResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}


@pytest.fixture
def db(monkeypatch):
    """target-A and target-B belong to user_A. target-C belongs to user_B."""
    fake = FakeClient()
    for targetId, owner in (("target-A", "user_A"), ("target-B", "user_A"), ("target-C", "user_B")):
        fake.tables["analysis_targets"].append(
            {"id": targetId, "owner_clerk_id": owner, "business_name": f"Business {targetId}", "platform": "GOOGLE_MAPS", "source_url": URL}
        )
    addReview(fake, "target-A", "r1", "Battery life is great")
    addReview(fake, "target-B", "r1", "Customer service was kind")
    addReview(fake, "target-C", "r1", "Parking was easy")
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


def addReview(db, targetId, reviewId, text):
    db.tables["reviews"].append(
        {"id": f"{targetId}-{reviewId}", "analysis_target_id": targetId, "review_text": text}
    )


def ask(targetId, user="user_A", question="What do people say?"):
    return main.ask_review_question(targetId, main.QuestionRequest(question=question), user)


def sent(call):
    return call["contents"][0]["parts"][0]["text"] + call["systemInstruction"]["parts"][0]["text"]


# ---- reviews are read fresh every time ---------------------------------------


def test_a_review_added_after_the_first_question_is_used_by_the_next_one(db, providerCalls):
    ask("target-A")
    addReview(db, "target-A", "r2", "Screen brightness is excellent")

    ask("target-A")

    assert "Screen brightness" not in sent(providerCalls[0])
    assert "Screen brightness" in sent(providerCalls[1])


def test_a_review_removed_after_the_first_question_is_no_longer_sent(db, providerCalls):
    ask("target-A")
    db.tables["reviews"] = [r for r in db.tables["reviews"] if r["analysis_target_id"] != "target-A"]

    result = ask("target-A")

    assert "No reviews have been ingested" in result["answer"]
    assert len(providerCalls) == 1  # the second question never reached the provider


def test_changing_target_B_does_not_change_what_is_sent_for_target_A(db, providerCalls):
    ask("target-A")
    ask("target-B")
    addReview(db, "target-B", "r2", "Staff were rude")

    ask("target-A")

    assert sent(providerCalls[0]) == sent(providerCalls[2])
    assert "Staff were rude" not in sent(providerCalls[2])


# ---- earlier questions are not remembered ------------------------------------


def test_the_previous_question_is_not_carried_into_the_next_request(db, providerCalls):
    ask("target-A", question="First question about batteries")
    ask("target-B", question="Second question about service")

    assert "First question about batteries" not in sent(providerCalls[1])
    assert "Second question about service" in sent(providerCalls[1])


# ---- user boundaries ---------------------------------------------------------


def test_another_user_cannot_get_target_A_context_after_the_owner_asked(db, providerCalls):
    ask("target-A")  # the owner asks first, which is when a cache would be filled

    with pytest.raises(main.HTTPException) as err:
        ask("target-A", user="user_B")

    assert err.value.status_code in (403, 404)
    assert len(providerCalls) == 1  # user_B's request never reached the provider


def test_another_users_question_on_their_own_target_has_none_of_user_As_reviews(db, providerCalls):
    ask("target-A")
    ask("target-B")

    ask("target-C", user="user_B")

    last = sent(providerCalls[-1])
    assert "Parking was easy" in last
    assert "Battery life" not in last
    assert "Customer service" not in last
