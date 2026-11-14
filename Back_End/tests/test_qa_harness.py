"""Tests for the Q&A boundary with the AI model (S2-003).

These use the `model` and `qa` tools from conftest.py. No real model is ever called,
so they are free to run and give the same result every time.
"""

import pytest
import requests

QUESTION = "What do people say about the staff?"
CAFE = ["Cafe espresso is great", "Cafe pastries are fresh", "Cafe staff were rude"]
BAKERY = ["Bakery sourdough is wonderful", "Bakery prices are high"]

# Text that appears only inside provider errors (it matches SECRET_DETAIL in conftest.py).
SECRET = "internal-secret-detail"


def askOk(qa, target, question=QUESTION, user="user_A"):
    response = qa.ask(target, question, user)
    assert response.status_code == 200, response.text
    return response


# ---- 1. the right system instructions are supplied ---------------------------


@pytest.mark.parametrize(
    "phrase",
    ["using only the provided review evidence", "never invent", "lack sufficient evidence", "decline"],
)
def test_system_instructions_set_the_rules_for_answering(qa, model, phrase):
    askOk(qa, qa.add_target("user_A", "Sample Cafe", CAFE))

    assert phrase in model.system_text.lower()


def test_system_instructions_name_the_active_business_and_platform(qa, model):
    askOk(qa, qa.add_target("user_A", "Sample Cafe", CAFE))

    assert "sample cafe" in model.system_text.lower()
    assert "google" in model.system_text.lower()


def test_system_instructions_change_with_the_active_target(qa, model):
    cafe = qa.add_target("user_A", "Sample Cafe", CAFE)
    bakery = qa.add_target("user_A", "Corner Bakery", BAKERY)

    askOk(qa, cafe)
    askOk(qa, bakery)

    first, second = (call.system_text.lower() for call in model.calls)
    assert "sample cafe" in first and "corner bakery" not in first
    assert "corner bakery" in second and "sample cafe" not in second


def test_system_instructions_are_the_same_for_every_question(qa, model):
    cafe = qa.add_target("user_A", "Sample Cafe", CAFE)

    askOk(qa, cafe, "What do people like?")
    askOk(qa, cafe, "What do people dislike?")

    assert model.calls[0].system_text == model.calls[1].system_text


def test_reviews_and_the_question_are_never_placed_in_the_system_instructions(qa, model):
    askOk(qa, qa.add_target("user_A", "Sample Cafe", CAFE), QUESTION)

    assert QUESTION not in model.system_text
    for review in CAFE:
        assert review not in model.system_text


# ---- 2. the right review context is supplied ---------------------------------


def test_every_review_of_the_target_is_sent_in_order(qa, model):
    askOk(qa, qa.add_target("user_A", "Sample Cafe", CAFE))

    assert model.evidence == CAFE


def test_the_question_is_sent_after_the_review_evidence(qa, model):
    askOk(qa, qa.add_target("user_A", "Sample Cafe", CAFE), QUESTION)

    assert model.prompt_text.startswith("Review Evidence:\n- Cafe espresso is great")
    assert model.prompt_text.endswith(f"User Question: {QUESTION}")
    assert model.question == QUESTION


def test_reviews_without_text_are_not_sent(qa, model):
    askOk(qa, qa.add_target("user_A", "Sample Cafe", ["Good", None, "", "Fine"]))

    assert model.evidence == ["Good", "Fine"]


def test_at_most_50_reviews_are_sent(qa, model):
    askOk(qa, qa.add_target("user_A", "Sample Cafe", [f"review {i:02d}" for i in range(60)]))

    assert len(model.evidence) == 50
    assert model.evidence[0] == "review 00"
    assert model.evidence[-1] == "review 49"


def test_each_question_makes_exactly_one_model_request(qa, model):
    askOk(qa, qa.add_target("user_A", "Sample Cafe", CAFE))

    assert model.call_count == 1


def test_the_request_goes_to_the_configured_address_with_the_key_in_a_header_only(qa, model):
    askOk(qa, qa.add_target("user_A", "Sample Cafe", CAFE))

    call = model.last
    assert call.url == qa.main.GEMINI_URL
    assert call.headers == {"x-goog-api-key": model.api_key}
    assert model.api_key not in call.url
    assert model.api_key not in str(call.payload)
    assert call.timeout == 15


# ---- 3. reviews for the wrong target are not supplied -------------------------


def test_only_the_asked_targets_reviews_are_sent(qa, model):
    cafe = qa.add_target("user_A", "Sample Cafe", CAFE)
    bakery = qa.add_target("user_A", "Corner Bakery", BAKERY)
    qa.add_reviews("a-deleted-target", "A review whose target no longer exists")

    askOk(qa, cafe)
    askOk(qa, bakery)

    cafeCall, bakeryCall = model.calls
    assert cafeCall.evidence == CAFE
    assert bakeryCall.evidence == BAKERY
    for text in BAKERY + ["Corner Bakery", "A review whose target no longer exists"]:
        assert text not in cafeCall.everything
    for text in CAFE + ["Sample Cafe", "A review whose target no longer exists"]:
        assert text not in bakeryCall.everything


def test_asking_about_a_target_that_does_not_exist_sends_nothing(qa, model):
    qa.add_target("user_A", "Sample Cafe", CAFE)

    response = qa.ask("no-such-target")

    assert response.status_code == 404
    assert model.call_count == 0


# ---- 4. another user's reviews are not supplied -------------------------------


def test_another_users_reviews_are_never_sent(qa, model):
    theirs = qa.add_target("user_A", "Sample Cafe", ["Private review of user A"])
    mine = qa.add_target("user_B", "Sample Cafe", ["Public review of user B"])

    denied = qa.ask(theirs, as_user="user_B")

    assert denied.status_code in (403, 404)
    assert "Private review of user A" not in denied.text
    assert model.call_count == 0  # the model was never contacted
    assert "reviews" not in qa.db.accessed  # and no review was even read

    askOk(qa, mine, user="user_B")
    assert model.evidence == ["Public review of user B"]
    assert "Private review of user A" not in model.last.everything


# ---- 5. the application behaves correctly for controlled model responses ------


def test_the_models_answer_is_returned_unchanged(qa, model):
    text = "Line one.\n\nCafé ☕ is praised in 2 of 3 reviews — see below."
    model.will_answer(text)

    response = askOk(qa, qa.add_target("user_A", "Sample Cafe", CAFE))

    assert response.json() == {"answer": text}


def test_a_recorded_provider_response_is_read_correctly(qa, model, recorded):
    model.will_return(recorded["answer"])

    response = askOk(qa, qa.add_target("user_A", "Sample Cafe", CAFE))

    assert response.json() == {"answer": "Customers praise the espresso."}


def test_only_the_first_part_of_the_first_candidate_is_used(qa, model, recorded):
    model.will_return(recorded["two_candidates"])

    response = askOk(qa, qa.add_target("user_A", "Sample Cafe", CAFE))

    assert response.json() == {"answer": "First answer."}


def test_a_target_with_no_reviews_gets_a_message_and_costs_nothing(qa, model):
    response = askOk(qa, qa.add_target("user_A", "Sample Cafe", []))

    assert "No reviews have been ingested" in response.json()["answer"]
    assert model.call_count == 0


def test_reviews_without_any_text_get_a_message_and_cost_nothing(qa, model):
    response = askOk(qa, qa.add_target("user_A", "Sample Cafe", [None, ""]))

    assert response.json()["answer"] == "The ingested reviews do not contain any text at the moment."
    assert model.call_count == 0


@pytest.mark.parametrize(
    "failure",
    [
        requests.ConnectionError(f"could not connect {SECRET}"),
        requests.Timeout(f"timed out {SECRET}"),
        429,
        500,
    ],
    ids=["connection-error", "timeout", "http-429", "http-500"],
)
def test_a_provider_failure_gives_a_safe_message_and_no_details(qa, model, failure):
    model.will_fail(failure)

    response = qa.ask(qa.add_target("user_A", "Sample Cafe", CAFE))

    assert response.status_code == 502
    assert response.json()["detail"] == "Failed to connect to AI provider. Please try again."
    assert SECRET not in response.text
    assert model.api_key not in response.text
    assert model.call_count == 1  # the app does not retry on its own


@pytest.mark.parametrize(
    "name", ["safety_block", "no_candidates", "no_parts", "no_text"]
)
def test_a_provider_response_without_an_answer_gives_a_safe_message(qa, model, recorded, name):
    model.will_return(recorded[name])

    response = qa.ask(qa.add_target("user_A", "Sample Cafe", CAFE))

    assert response.status_code == 502
    assert response.json()["detail"] == "Failed to process AI response."


@pytest.mark.parametrize("payload", [None, {}, "not an object", {"candidates": None}], ids=["none", "empty", "text", "null-list"])
def test_a_malformed_provider_response_gives_a_safe_message(qa, model, payload):
    model.will_return(payload)

    response = qa.ask(qa.add_target("user_A", "Sample Cafe", CAFE))

    assert response.status_code == 502
    assert response.json()["detail"] == "Failed to process AI response."


def test_a_failed_request_does_not_affect_the_next_one(qa, model):
    model.script(model.failure(requests.ConnectionError("down")), model.answer("Back again."))
    cafe = qa.add_target("user_A", "Sample Cafe", CAFE)

    first = qa.ask(cafe)
    second = qa.ask(cafe)

    assert first.status_code == 502
    assert second.status_code == 200
    assert second.json() == {"answer": "Back again."}
    assert model.calls[0].evidence == model.calls[1].evidence == CAFE


# ---- questions the app refuses before the model is involved -------------------


@pytest.mark.parametrize("question", ["", "q" * 1001], ids=["empty", "too-long"])
def test_an_invalid_question_is_rejected_without_calling_the_model(qa, model, question):
    response = qa.ask(qa.add_target("user_A", "Sample Cafe", CAFE), question)

    assert response.status_code == 422
    assert model.call_count == 0


def test_a_question_at_the_length_limit_is_sent_in_full(qa, model):
    question = "q" * 1000

    askOk(qa, qa.add_target("user_A", "Sample Cafe", CAFE), question)

    assert model.question == question


def test_a_missing_api_key_stops_the_request_before_the_model_is_called(qa, model, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    response = qa.ask(qa.add_target("user_A", "Sample Cafe", CAFE))

    assert response.status_code == 503
    assert model.call_count == 0


# ---- the harness itself: no test can spend money by accident ------------------


def test_a_real_request_to_the_ai_provider_is_blocked_and_reported(no_live_network):
    with pytest.raises(RuntimeError, match="Blocked"):
        requests.post("https://generativelanguage.googleapis.com/v1beta/models/x:generateContent", json={})

    assert len(no_live_network) == 1
    no_live_network.clear()  # this test blocked it on purpose, so it is not a failure


def test_a_real_request_to_the_review_provider_is_blocked_and_reported(no_live_network):
    with pytest.raises(RuntimeError, match="Blocked"):
        requests.get("https://api.openwebninja.com/local-business-data/business-reviews-v2")

    assert len(no_live_network) == 1
    no_live_network.clear()
