"""Shared test tools for the backend tests.

Q&A test harness (S2-003)
-------------------------
Nothing in these tests calls a real AI model, so CI costs nothing and gives the same
answer every time. Two parts make that possible:

  * `model` stands in for the AI provider. It records everything the app sends
    (the address, the headers, the system instructions, the review evidence and the
    question) and answers from a script that the test controls.
  * `qa` is a small app setup: an in-memory database with targets and reviews for
    different users, and a way to ask a question as a chosen user through the real
    HTTP route.

A safety net runs around every test (`no_live_network`). If any test, by mistake, tries
to make a real request to the AI provider or the review provider, the request is blocked
and the test fails with a message saying so. That is what stops accidental spending.

How to use `model`
    model.will_answer("text", "second text")     answers in order; the last one repeats
    model.will_return(payload)                   returns a raw provider payload
    model.will_fail(ConnectionError("x"))        raises that error when called
    model.will_fail(429)                         fails like an HTTP error with that status
    model.script(model.answer("a"), model.failure(500), model.answer("b"))
                                                 a mixed sequence of outcomes
    model.calls, model.last, model.call_count    what the app sent
    model.system_text / prompt_text / evidence / question   parts of the last request
"""

import json as jsonlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import re
from types import SimpleNamespace

import pytest
import requests

API_KEY = "test-key"
# Text that appears only inside provider errors. It must never reach a user.
SECRET_DETAIL = "internal-secret-detail"


def refreshRpc(db, name, params):
    def execute():
        snapshot = deepcopy(db.tables)
        try:
            targetId = params["p_target_id"]
            target = next(t for t in db.tables["analysis_targets"] if t["id"] == targetId)
            if name == "begin_review_ingestion":
                for job in db.tables["ingestion_jobs"]:
                    if job["analysis_target_id"] != targetId or job["status"] not in ("pending", "running"):
                        continue
                    started = datetime.fromisoformat((job.get("started_at") or job["created_at"]).replace("Z", "+00:00"))
                    if started < datetime.now(timezone.utc) - timedelta(minutes=10):
                        job.update(status="failed", error_message="Ingestion did not finish. You can try again.")
                    else:
                        error = RuntimeError("Already running")
                        error.code = "55P03"
                        raise error
                return db.table("ingestion_jobs").insert({
                    "analysis_target_id": targetId, "status": "running",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "reviews_ingested": 0,
                }).execute()

            job = next(j for j in db.tables["ingestion_jobs"] if j["id"] == params["p_job_id"] and j["analysis_target_id"] == targetId)
            if job["status"] == "completed":
                return SimpleNamespace(data=[dict(job)])
            if job["status"] != "running":
                raise RuntimeError("Attempt is no longer active")
            if getattr(db, "failPromotion", False):
                raise RuntimeError("Promotion failed")
            keys = set()
            for row in params["p_reviews"]:
                def key(r):
                    sourceId = (r.get("google_review_id") or "").strip()
                    date = r.get("reviewed_at")
                    parsed = datetime.fromisoformat(date.replace("Z", "+00:00")) if date else None
                    stamp = (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp() if parsed else None
                    return ("source", sourceId) if sourceId else ("fingerprint", re.sub(r"\s+", " ", (r.get("review_text") or "").strip()).lower(), r["rating"], stamp)

                identity = key(row)
                if identity in keys:
                    continue
                keys.add(identity)
                match = next((r for r in db.tables["reviews"] if r["analysis_target_id"] == targetId and key(r) == identity), None)
                if match:
                    match.update(row, ingested_at=datetime.now(timezone.utc).isoformat())
                else:
                    db.table("reviews").insert({**row, "ingested_at": datetime.now(timezone.utc).isoformat()}).execute()
            job.update(status="completed", reviews_ingested=len(keys),
                       reviews_skipped=params["p_skipped"] + len(params["p_reviews"]) - len(keys),
                       completed_at=datetime.now(timezone.utc).isoformat(), error_message=None)
            target.update(current_ingestion_id=job["id"], current_ingestion_at=job["completed_at"])
            return SimpleNamespace(data=[dict(job)])
        except Exception:
            db.tables = snapshot
            raise
    return SimpleNamespace(execute=execute)


def answerPayload(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


class FakeProviderResponse:
    """Stands in for the response object that requests.post returns."""

    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


class Call:
    """One request the app sent to the AI provider."""

    def __init__(self, url, headers, payload, timeout):
        self.url = url
        self.headers = headers
        self.payload = payload
        self.timeout = timeout

    @property
    def system_text(self):
        return self.payload["systemInstruction"]["parts"][0]["text"]

    @property
    def prompt_text(self):
        return self.payload["contents"][0]["parts"][0]["text"]

    @property
    def evidence(self):
        """The review texts that were sent, in order."""
        head, separator, _ = self.prompt_text.rpartition("\n\nUser Question: ")
        assert separator, "The prompt has no 'User Question:' section."
        assert head.startswith("Review Evidence:\n"), "The prompt has no 'Review Evidence:' section."
        lines = head[len("Review Evidence:\n"):].split("\n")
        assert all(line.startswith("- ") for line in lines), f"Evidence lines must start with '- ': {lines}"
        return [line[2:] for line in lines]

    @property
    def question(self):
        return self.prompt_text.rpartition("\n\nUser Question: ")[2]

    @property
    def everything(self):
        """All the text of the request, for checking that something was not sent."""
        return self.url + jsonlib.dumps(self.headers) + jsonlib.dumps(self.payload)


class ScriptedModel:
    """The AI provider, replaced. Records requests and answers from a script."""

    api_key = API_KEY

    def __init__(self):
        self.calls = []
        self.steps = [self.answer("Scripted answer.")]
        self.position = 0

    # -- what the model does when called ---------------------------------------

    def __call__(self, url, headers=None, json=None, timeout=None, **kwargs):
        self.calls.append(Call(url, headers, json, timeout))
        step = self.steps[min(self.position, len(self.steps) - 1)]
        self.position += 1
        return step()

    # -- building outcomes -----------------------------------------------------

    def answer(self, text):
        return lambda: FakeProviderResponse(answerPayload(text))

    def payload(self, payload):
        return lambda: FakeProviderResponse(payload)

    def failure(self, failure):
        """An Exception is raised as it is. A number fails like an HTTP error with that status."""
        if isinstance(failure, Exception):
            def raiseIt():
                raise failure
            return raiseIt

        def httpError():
            response = requests.Response()
            response.status_code = failure
            response._content = jsonlib.dumps({"error": {"message": SECRET_DETAIL}}).encode()
            error = requests.HTTPError(
                f"{failure} Error for url: https://example.test/?key={API_KEY} {SECRET_DETAIL}", response=response
            )
            return FakeProviderResponse(error=error)

        return httpError

    def script(self, *steps):
        self.steps = list(steps)
        self.position = 0

    def will_answer(self, *texts):
        self.script(*[self.answer(text) for text in texts])

    def will_return(self, payload):
        self.script(self.payload(payload))

    def will_fail(self, failure):
        self.script(self.failure(failure))

    # -- looking at what was sent ----------------------------------------------

    @property
    def call_count(self):
        return len(self.calls)

    @property
    def last(self):
        assert self.calls, "The model was never called."
        return self.calls[-1]

    @property
    def system_text(self):
        return self.last.system_text

    @property
    def prompt_text(self):
        return self.last.prompt_text

    @property
    def evidence(self):
        return self.last.evidence

    @property
    def question(self):
        return self.last.question


# ---- a small app setup for Q&A tests ------------------------------------------


class QaQuery:
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
        data = [dict(r) for r in self.rows if all(f(r) for f in self.filters)]
        return SimpleNamespace(data=data)


class QaDatabase:
    def __init__(self):
        self.tables = {"analysis_targets": [], "reviews": []}
        self.accessed = []  # names of the tables that were queried, in order

    def table(self, name):
        self.accessed.append(name)
        return QaQuery(self.tables[name])


class QaApp:
    """An in-memory database plus a way to ask questions as a chosen user."""

    def __init__(self, monkeypatch):
        from fastapi.testclient import TestClient

        from app import main

        self.main = main
        self.db = QaDatabase()
        monkeypatch.setattr(main, "supabaseClient", self.db)
        self.client = TestClient(main.app)
        self.targets = 0

    def add_target(self, owner, name, reviews=(), platform="GOOGLE_MAPS"):
        self.targets += 1
        targetId = f"target-{self.targets}"
        self.db.tables["analysis_targets"].append(
            {
                "id": targetId,
                "owner_clerk_id": owner,
                "business_name": name,
                "platform": platform,
                "source_url": "https://www.google.com/maps/place/x/data=!1s0x1:0x2",
            }
        )
        self.add_reviews(targetId, *reviews)
        return targetId

    def add_reviews(self, targetId, *texts):
        for text in texts:
            number = len(self.db.tables["reviews"]) + 1
            self.db.tables["reviews"].append(
                {"id": f"review-{number}", "analysis_target_id": targetId, "review_text": text, "rating": 5}
            )

    def ask(self, targetId, question="What do people say?", as_user="user_A"):
        self.main.app.dependency_overrides[self.main.getCurrentUserId] = lambda: as_user
        return self.client.post(f"/api/targets/{targetId}/ask", json={"question": question})


# ---- fixtures -----------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    """Block real requests to outside services in every test, so tests never cost money."""
    blocked = []

    def refuse(kind):
        def guard(url, *args, **kwargs):
            blocked.append(f"{kind} {url}")
            raise RuntimeError(f"Blocked: a test tried to make a real {kind} request to {url}. Fake it instead.")

        return guard

    monkeypatch.setattr(requests, "post", refuse("POST"))
    monkeypatch.setattr(requests, "get", refuse("GET"))
    yield blocked
    # Some code catches every error, so also fail here if anything was blocked.
    assert not blocked, f"These real requests were attempted and blocked: {blocked}"


@pytest.fixture
def model(monkeypatch):
    """The AI provider, replaced by a scripted stand-in."""
    from app import main

    scripted = ScriptedModel()
    monkeypatch.setenv("GEMINI_API_KEY", API_KEY)
    monkeypatch.setattr(main.requests, "post", scripted)
    return scripted


@pytest.fixture
def qa(monkeypatch):
    """A small app with an in-memory database, for asking questions as different users."""
    from app import main

    app = QaApp(monkeypatch)
    yield app
    main.app.dependency_overrides.clear()


@pytest.fixture
def recorded():
    """Realistic provider responses, written out once so that no live model is needed."""
    return {
        "answer": {
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"text": "Customers praise the espresso."}]},
                    "finishReason": "STOP",
                    "index": 0,
                }
            ],
            "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 8, "totalTokenCount": 128},
        },
        "two_candidates": {
            "candidates": [
                {"content": {"role": "model", "parts": [{"text": "First answer."}, {"text": "Second part."}]}},
                {"content": {"role": "model", "parts": [{"text": "Other candidate."}]}},
            ]
        },
        "safety_block": {"promptFeedback": {"blockReason": "SAFETY"}},
        "no_candidates": {"candidates": []},
        "no_parts": {"candidates": [{"content": {"role": "model"}, "finishReason": "MAX_TOKENS"}]},
        "no_text": {"candidates": [{"content": {"role": "model", "parts": [{}]}, "finishReason": "OTHER"}]},
    }
