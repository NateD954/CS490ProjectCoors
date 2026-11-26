"""Run the scope-guard evaluation set against the REAL model (S2-004).

This calls the real AI provider, so it costs a few cents and is NOT part of CI.
Run it by hand from the Back_End folder, with GEMINI_API_KEY set (in .env or the shell):

    python -m evals.run_scope_guard_eval
    python -m evals.run_scope_guard_eval --runs 3            # repeat each question 3 times
    python -m evals.run_scope_guard_eval --category other_platform --verbose

It goes through the real Q&A code (app.main.ask_review_question) with an in-memory
database holding only this evaluation's reviews. The exit code is 1 if any case fails.
"""

import argparse
import os
import sys
import time
from types import SimpleNamespace

# The app refuses to import without database settings. This run never uses the real
# database, so harmless placeholders are enough (CI does the same).
os.environ.setdefault("SUPABASE_URL", "https://placeholder.supabase.co")
os.environ.setdefault("SUPABASE_SECRET_KEY", "placeholder.placeholder.placeholder")

from fastapi import HTTPException  # noqa: E402

from app import main  # noqa: E402
from evals.scope_guard_cases import BUSINESS_NAME, CASES, PLATFORM, REVIEWS  # noqa: E402
from evals.scope_guard_grading import grade  # noqa: E402

TARGET_ID = "eval-target"
USER_ID = "eval-user"


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []

    def select(self, *_):
        return self

    def order(self, *_, **__):
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def execute(self):
        return SimpleNamespace(data=[dict(r) for r in self.rows if all(f(r) for f in self.filters)])


class _Database:
    def __init__(self):
        self.tables = {
            "analysis_targets": [
                {
                    "id": TARGET_ID,
                    "owner_clerk_id": USER_ID,
                    "business_name": BUSINESS_NAME,
                    "platform": PLATFORM,
                    "source_url": "https://www.google.com/maps/place/x/data=!1s0x1:0x2",
                }
            ],
            "reviews": [
                {"id": f"review-{i}", "analysis_target_id": TARGET_ID, "review_text": text, "rating": 5}
                for i, text in enumerate(REVIEWS, start=1)
            ],
        }

    def table(self, name):
        return _Query(self.tables[name])


def make_database():
    """An in-memory database holding only the evaluation's business and reviews."""
    return _Database()


def ask(question: str) -> str:
    """Ask one question through the real Q&A code and return the answer text."""
    return main.ask_review_question(TARGET_ID, main.QuestionRequest(question=question), USER_ID)["answer"]


def evaluate(ask_fn, cases, runs=1, delay=0.0):
    """Ask every case `runs` times and grade each answer. A provider error counts as a failure."""
    results = []
    for case in cases:
        attempts = []
        for _ in range(runs):
            try:
                response = ask_fn(case["question"])
                verdict = grade(case, response)
                attempts.append({"passed": verdict.passed, "reason": verdict.reason, "response": response})
            except HTTPException as err:
                attempts.append({"passed": False, "reason": f"error {err.status_code}: {err.detail}", "response": ""})
            if delay:
                time.sleep(delay)
        results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "question": case["question"],
                "passed": all(a["passed"] for a in attempts),
                "attempts": attempts,
            }
        )
    return results


def report(results, verbose=False):
    for r in results:
        print(f"{'PASS' if r['passed'] else 'FAIL'}  {r['category']:<22} {r['id']}")
        if verbose or not r["passed"]:
            for a in r["attempts"]:
                print(f"      Q: {r['question']}")
                print(f"      {'ok ' if a['passed'] else 'bad'}: {a['reason']}")
                print(f"      A: {a['response'][:400]!r}")
    failed = [r for r in results if not r["passed"]]
    print(f"\n{len(results) - len(failed)} of {len(results)} cases passed.")
    return len(failed)


def run(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=1, help="times to ask each question (all must pass)")
    parser.add_argument("--category", help="only run one category, e.g. other_platform")
    parser.add_argument("--delay", type=float, default=0.5, help="seconds to wait between requests")
    parser.add_argument("--verbose", action="store_true", help="show every answer, not just failures")
    args = parser.parse_args(argv)

    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set. Put it in Back_End/.env or export it, then try again.")
        return 2

    cases = [c for c in CASES if not args.category or c["category"] == args.category]
    if not cases:
        print(f"No cases in category {args.category!r}.")
        return 2

    main.supabaseClient = make_database()
    print(f"Asking {len(cases)} questions x {args.runs} run(s) about {BUSINESS_NAME!r}...\n")
    failures = report(evaluate(ask, cases, runs=args.runs, delay=args.delay), verbose=args.verbose)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
