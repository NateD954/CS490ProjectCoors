import pytest
import requests
from app import main

URL = "https://www.google.com/maps/place/Chipotle/data=!1s0x89c2fa2bfb0d27d5:0xcceef158b20fbf10"
API_KEY = "secret-key"


class FakeQuery:
    """Tiny in-memory stand-in for the Supabase query builder."""

    def __init__(self, rows):
        self.rows = rows
        self.filters = []

    def select(self, *_):
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def execute(self):
        data = [r for r in self.rows if all(f(r) for f in self.filters)]
        return type("Result", (), {"data": data})()


class FakeClient:
    def __init__(self):
        self.tables = {"analysis_targets": [], "reviews": []}

    def table(self, name):
        return FakeQuery(self.tables[name])


class FakeProviderResponse:
    """Stands in for the response object returned by requests.post."""

    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


def answerPayload(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


@pytest.fixture
def client(monkeypatch):
    """One target owned by user_A. Its reviews are added by each test."""
    fake = FakeClient()
    fake.tables["analysis_targets"].append(
        {"id": "target-A", "owner_clerk_id": "user_A", "business_name": "A's Cafe", "platform": "GOOGLE_MAPS", "source_url": URL}
    )
    monkeypatch.setattr(main, "supabaseClient", fake)
    monkeypatch.setenv("GEMINI_API_KEY", API_KEY)
    return fake


def addReviews(client, *texts, target="target-A"):
    for i, text in enumerate(texts):
        client.tables["reviews"].append(
            {"id": f"{target}-r{i}", "analysis_target_id": target, "review_text": text}
        )


def providerReturns(monkeypatch, outcome):
    """Replace requests.post. outcome is a response to return or an exception to raise."""
    calls = []

    def fakePost(url, **kwargs):
        calls.append({"url": url, **kwargs})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(main.requests, "post", fakePost)
    return calls


def ask(question="What do people like?", user="user_A"):
    return main.ask_review_question("target-A", main.QuestionRequest(question=question), user)


def promptSent(calls):
    return calls[0]["json"]["contents"][0]["parts"][0]["text"]


# Provider failures whose text includes the API key, like real requests errors do.
badResponse = requests.Response()
badResponse.status_code = 400
badResponse._content = f'{{"error": "API key invalid: {API_KEY}"}}'.encode()

PROVIDER_FAILURES = [
    requests.ConnectionError(f"Max retries exceeded for url: https://example.test/ask?key={API_KEY}"),
    requests.HTTPError(f"400 Client Error for url: https://example.test/ask?key={API_KEY}", response=badResponse),
]


# ---- who may ask -------------------------------------------------------------


def test_another_user_cannot_ask_about_a_target(client, monkeypatch):
    addReviews(client, "Secret review text")
    calls = providerReturns(monkeypatch, FakeProviderResponse(answerPayload("never sent")))

    with pytest.raises(main.HTTPException) as err:
        ask(user="user_B")

    assert err.value.status_code in (403, 404)
    assert "Secret review text" not in str(err.value.detail)
    assert calls == []  # the AI provider was never contacted


# ---- no usable reviews -------------------------------------------------------


def test_no_reviews_returns_a_message_and_does_not_call_the_provider(client, monkeypatch):
    calls = providerReturns(monkeypatch, FakeProviderResponse(answerPayload("never sent")))

    result = ask()

    assert "No reviews have been ingested" in result["answer"]
    assert calls == []


def test_reviews_without_text_return_a_message_and_do_not_call_the_provider(client, monkeypatch):
    addReviews(client, None, "")
    calls = providerReturns(monkeypatch, FakeProviderResponse(answerPayload("never sent")))

    result = ask()

    assert result["answer"] == "The ingested reviews do not contain any text at the moment."
    assert calls == []


# ---- a successful answer -----------------------------------------------------


def test_answer_is_returned_and_only_this_targets_reviews_are_sent(client, monkeypatch):
    addReviews(client, "Great tacos", "Slow service")
    addReviews(client, "Other target secret", target="target-B")
    calls = providerReturns(monkeypatch, FakeProviderResponse(answerPayload("People like the tacos.")))

    result = ask("What do people like?")

    assert result == {"answer": "People like the tacos."}
    prompt = promptSent(calls)
    assert "- Great tacos" in prompt
    assert "- Slow service" in prompt
    assert "What do people like?" in prompt
    assert "Other target secret" not in prompt
    assert len(calls) == 1


def test_only_the_first_50_reviews_are_sent(client, monkeypatch):
    addReviews(client, *[f"text-{i:02d}" for i in range(60)])
    calls = providerReturns(monkeypatch, FakeProviderResponse(answerPayload("ok")))

    ask()

    prompt = promptSent(calls)
    assert "text-49" in prompt
    assert "text-50" not in prompt


# ---- system prompt ------------------------------------------------------------

def test_system_prompt(client, monkeypatch):
    addReviews(client, "Great tacos")

    calls = providerReturns(
        monkeypatch,
        FakeProviderResponse(answerPayload("ok"))
    )

    ask()

    prompt = calls[0]["json"]["systemInstruction"]["parts"][0]["text"]

    assert "A's Cafe" in prompt
    assert "GOOGLE_MAPS" in prompt
    assert "review evidence" in prompt
    assert "general-knowledge" in prompt
    assert "other businesses" in prompt
    assert "review platforms" in prompt

# ---- provider failures -------------------------------------------------------


@pytest.mark.parametrize("failure", PROVIDER_FAILURES)
def test_provider_failure_gives_a_safe_error_message(client, monkeypatch, failure):
    addReviews(client, "Great tacos")
    providerReturns(monkeypatch, failure)

    with pytest.raises(main.HTTPException) as err:
        ask()

    assert err.value.status_code in (500, 502)
    assert err.value.detail == "Failed to connect to AI provider. Please try again."
    assert API_KEY not in str(err.value.detail)


@pytest.mark.parametrize("failure", PROVIDER_FAILURES)
def test_provider_failure_does_not_leak_the_api_key_to_the_logs(client, monkeypatch, capsys, caplog, failure):
    addReviews(client, "Great tacos")
    providerReturns(monkeypatch, failure)

    with pytest.raises(main.HTTPException):
        ask()

    printed = capsys.readouterr()
    assert API_KEY not in printed.out
    assert API_KEY not in printed.err
    assert API_KEY not in caplog.text


@pytest.mark.parametrize(
    "payload",
    [{}, {"candidates": []}, {"candidates": [{"content": {}}]}],
)
def test_unexpected_provider_response_gives_a_safe_error_message(client, monkeypatch, payload):
    addReviews(client, "Great tacos")
    providerReturns(monkeypatch, FakeProviderResponse(payload))

    with pytest.raises(main.HTTPException) as err:
        ask()

    assert err.value.status_code in (500, 502)
    assert err.value.detail == "Failed to process AI response."

def test_missing_api_key_gives_a_clear_error_and_does_not_call_the_provider(client, monkeypatch):
    addReviews(client, "Great tacos")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    calls = providerReturns(monkeypatch, FakeProviderResponse(answerPayload("never sent")))

    with pytest.raises(main.HTTPException) as err:
        ask()

    assert err.value.status_code == 503
    assert calls == []