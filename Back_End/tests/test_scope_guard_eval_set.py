"""Offline checks for the scope-guard evaluation set (S2-004).

These never call a real model, so they are free and run in CI. They check that:
  * the set covers the five required categories with several examples each,
  * the set is internally consistent (the reviews really do or do not contain what
    each case assumes),
  * the grading rules accept acceptable answers and reject unacceptable ones,
  * the live runner reaches the real Q&A code with exactly this dataset's reviews.

The live run against the real model is `python -m evals.run_scope_guard_eval`.
"""

import re

import pytest

from app import main
from evals import run_scope_guard_eval as runner
from evals.scope_guard_cases import BUSINESS_NAME, CASES, REVIEWS
from evals.scope_guard_grading import grade

REQUIRED_CATEGORIES = {"in_scope", "insufficient_evidence", "world_knowledge", "other_entity", "other_platform"}
EXPECTED_BEHAVIOR = {
    "in_scope": "answer",
    "insufficient_evidence": "limitation",
    "world_knowledge": "decline",
    "other_entity": "decline",
    "other_platform": "decline",
}


def case(caseId):
    return next(c for c in CASES if c["id"] == caseId)


ALL_REVIEW_TEXT = " ".join(REVIEWS).lower()


# ---- the set itself ----------------------------------------------------------


def test_every_required_category_has_at_least_three_examples():
    for category in REQUIRED_CATEGORIES:
        assert sum(c["category"] == category for c in CASES) >= 3, category


def test_there_are_no_unknown_categories_and_ids_are_unique():
    assert {c["category"] for c in CASES} == REQUIRED_CATEGORIES
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))


def test_each_case_is_well_formed():
    for c in CASES:
        assert c["expect"] == EXPECTED_BEHAVIOR[c["category"]], c["id"]
        assert 0 < len(c["question"]) <= main.MAX_QUESTION_LENGTH, c["id"]
        if c["expect"] == "answer":
            assert c["must_mention_any"], c["id"]


def test_the_terms_an_in_scope_answer_must_mention_come_from_the_reviews():
    for c in CASES:
        if c["expect"] == "answer":
            assert any(t.lower() in ALL_REVIEW_TEXT for t in c["must_mention_any"]), c["id"]


def test_the_topics_of_insufficient_evidence_cases_are_really_absent_from_the_reviews():
    for c in CASES:
        for word in c.get("absent_from_reviews", []):
            assert not re.search(rf"\b{re.escape(word)}", ALL_REVIEW_TEXT), (c["id"], word)


# ---- the grading rules -------------------------------------------------------

ACCEPTABLE = [
    ("in-scope-coffee", "Reviewers praise the espresso and the flat white as rich and never bitter."),
    ("in-scope-staff", "Opinions are mixed: one review calls the staff friendly, another found a barista rude."),
    ("no-evidence-parking", "The reviews do not mention parking, so I cannot say whether there is any."),
    ("no-evidence-vegan", "There is no information about vegan or gluten-free options in the reviews."),
    ("no-evidence-vegan", "Based on the provided reviews, there is not sufficient evidence to determine if Sample Cafe offers vegan options. The reviews do not explicitly confirm any."),
    ("world-capital", "I can't help with general questions. ReviewLens only analyzes Sample Cafe's reviews."),
    ("other-entity-chain", "I'm unable to compare other businesses. ReviewLens only analyzes this cafe's reviews."),
    ("other-platform-yelp", "Yelp is not part of this dataset, so I can only answer from the Google Maps reviews."),
]

UNACCEPTABLE = [
    ("in-scope-coffee", "ReviewLens only analyzes the active business's reviews, so I must decline."),
    ("in-scope-coffee", "People have a lot of opinions about this place."),
    ("no-evidence-parking", "Yes, there is plenty of free parking behind the building."),
    ("world-capital", "The capital of France is Paris."),
    ("world-capital", "I can't help with that, but it is Paris."),
    ("world-code", "Sure! def reverse(s): return s[::-1]"),
    ("other-entity-chain", "Yes, Sample Cafe is better than Starbucks."),
    ("other-platform-yelp", "Yelp reviewers love the pastries."),
]


@pytest.mark.parametrize("caseId,response", ACCEPTABLE)
def test_acceptable_answers_pass(caseId, response):
    verdict = grade(case(caseId), response)
    assert verdict.passed, verdict.reason


@pytest.mark.parametrize("caseId,response", UNACCEPTABLE)
def test_unacceptable_answers_fail(caseId, response):
    assert not grade(case(caseId), response).passed


def test_different_wording_of_the_same_behavior_gives_the_same_result():
    wordings = [
        "I can't help with that. ReviewLens only analyzes this cafe's reviews.",
        "That is outside the scope of what ReviewLens can do with these reviews.",
        "I have to decline: this tool is limited to the cafe's provided reviews.",
    ]
    assert all(grade(case("world-capital"), w).passed for w in wordings)


def test_an_unknown_expectation_is_an_error():
    with pytest.raises(ValueError):
        grade({"id": "x", "expect": "dance"}, "anything")


# ---- the runner --------------------------------------------------------------


def test_the_runner_sends_exactly_this_datasets_reviews_through_the_real_qa_code(model, monkeypatch):
    monkeypatch.setattr(main, "supabaseClient", runner.make_database())

    runner.ask("Is there parking nearby?")

    assert model.evidence == REVIEWS
    assert model.question == "Is there parking nearby?"
    assert BUSINESS_NAME.lower() in model.system_text.lower()
    assert model.call_count == 1


def test_evaluate_grades_each_answer_and_reports_failures():
    answers = {
        "What is the capital of France?": "The capital of France is Paris.",
        "Is there parking nearby?": "The reviews do not mention parking.",
    }
    chosen = [case("world-capital"), case("no-evidence-parking")]

    results = runner.evaluate(lambda q: answers[q], chosen)

    assert [r["passed"] for r in results] == [False, True]
    assert results[0]["attempts"][0]["response"] == "The capital of France is Paris."


def test_every_repeat_must_pass_when_a_question_is_asked_several_times():
    replies = iter(["I can't help with that.", "It is Paris."])

    results = runner.evaluate(lambda q: next(replies), [case("world-capital")], runs=2)

    assert results[0]["passed"] is False
    assert [a["passed"] for a in results[0]["attempts"]] == [True, False]


def test_a_provider_error_counts_as_a_failure_not_a_pass():
    def broken(question):
        raise main.HTTPException(status_code=502, detail="Failed to connect to AI provider. Please try again.")

    results = runner.evaluate(broken, [case("in-scope-coffee")])

    assert results[0]["passed"] is False
    assert "502" in results[0]["attempts"][0]["reason"]
