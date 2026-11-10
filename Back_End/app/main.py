import logging
import requests
import os
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.db import supabaseClient
from app.auth import getCurrentUserId
from app.target_repository import saveTarget, listTargetsForOwner
from services.google_reviews import getGoogleDataIdFromURL, getGooglePlaceData, extractReviews

logger = logging.getLogger(__name__)

app = FastAPI(title="ReviewLens Coors edition (/^-^)o日日o(|^0^|) Backend Fastest API")
    
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

class TargetCreateRequest(BaseModel):
    name: str
    platform: str
    sourceUrl: str

MAX_QUESTION_LENGTH = 1000  # keep in step with the limit in the frontend's ReviewQA component

class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)

# The key is sent in a header, never in the URL, so it cannot end up in logs or error text.
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent"

def saveReviews(rows: list) -> None:
    for attempt in range(2):
        try:
            supabaseClient.table("reviews").upsert(rows, on_conflict="analysis_target_id,google_review_id").execute()
            return
        except Exception:
            if attempt == 1:
                raise

JOB_STATUS_TO_UI = {"pending": "in_progress", "running": "in_progress", "completed": "completed", "failed": "failed"}
STALE_JOB_AFTER = timedelta(minutes=10)

def withIngestionStatus(targets: list) -> list:
    if not targets:
        return targets
    ids = [t["id"] for t in targets]
    jobs = (
        supabaseClient.table("ingestion_jobs")
        .select("analysis_target_id,status,error_message,created_at")
        .in_("analysis_target_id", ids)
        .order("created_at", desc=True)
        .execute()
        .data
    )
    latest = {}
    for job in jobs:
        latest.setdefault(job["analysis_target_id"], job)

    for t in targets:
        job = latest.get(t["id"])
        state, error = "not_started", None
        if job:
            state = JOB_STATUS_TO_UI.get(job["status"], "not_started")
            error = job.get("error_message")
            started = datetime.fromisoformat(job["created_at"].replace("Z", "+00:00"))
            if state == "in_progress" and datetime.now(timezone.utc) - started > STALE_JOB_AFTER:
                state, error = "failed", "Ingestion did not finish. You can try again."
        t["ingestion_status"] = state
        t["ingestion_error"] = error
    return targets

def isGoogleUrl(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme in ("http", "https") and (host == "google.com" or host.endswith(".google.com"))

def nowIso() -> str:
    return datetime.now(timezone.utc).isoformat()

def fieldError(field: str, message: str) -> dict:
    return {"loc": ["body", field], "msg": message}

def verifyTargetOwnership(targetId: str, authenticatedUserId: str) -> dict:
    res = supabaseClient.table("analysis_targets").select("*").eq("id", targetId).execute()
    if not res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found. Please check the target ID and try again.")

    target = res.data[0]
    if target.get("owner_clerk_id") != authenticatedUserId:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Analysis target access violation. Please check the target ID and user ID and try again."
        )
    return target

@app.post("/api/targets", status_code=status.HTTP_201_CREATED)
def createTarget(body: TargetCreateRequest, userId: str = Depends(getCurrentUserId)):
    name = body.name.strip()
    sourceUrl = body.sourceUrl.strip()
    dataId = getGoogleDataIdFromURL(sourceUrl)

    errors = []
    if not name:
        errors.append(fieldError("name", "Enter the business or location name."))
    if not isGoogleUrl(sourceUrl) or not dataId:
        errors.append(fieldError("sourceUrl", "Enter the full Google Maps link for the place."))
    if body.platform != "GOOGLE_MAPS":
        errors.append(fieldError("platform", "Unsupported review platform."))
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors)

    return saveTarget(supabaseClient, userId, dataId, name, sourceUrl)

@app.get("/api/targets")
def listTargets(userId: str = Depends(getCurrentUserId)):
    return withIngestionStatus(listTargetsForOwner(supabaseClient, userId))

@app.get("/api/targets/{targetId}")
def getTarget(targetId: str, userId: str = Depends(getCurrentUserId)):
    return withIngestionStatus([verifyTargetOwnership(targetId, userId)])[0]

@app.get("/api/targets/{targetId}/reviews")
def getTargetReviews(
    targetId: str,
    userId: str = Depends(getCurrentUserId),
    limit: Optional[int] = Query(None, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    verifyTargetOwnership(targetId, userId)
    query = (
        supabaseClient.table("reviews")
        .select("*")
        .eq("analysis_target_id", targetId)
        .order("reviewed_at", desc=True, nullsfirst=False)
        .order("id")
    )
    if limit is not None:
        query = query.range(offset, offset + limit - 1)
    return query.execute().data

@app.post("/api/targets/{targetId}/ingest")
def ingestTarget(targetId: str, userId: str = Depends(getCurrentUserId)):
    target = verifyTargetOwnership(targetId, userId)

    job = supabaseClient.table("ingestion_jobs").insert({
        "analysis_target_id": targetId,
        "status": "running",
        "started_at": nowIso()
    }).execute().data[0]

    try:
        dataId = getGoogleDataIdFromURL(target["source_url"])
        if not dataId:
            raise ValueError("The target's source URL does not contain a Google Maps place id.")

        reviews = extractReviews(getGooglePlaceData(dataId))
        rows = [
            {
                "analysis_target_id": targetId,
                "google_review_id": r["reviewId"],
                "rating": int(r["rating"]),
                "review_text": r["reviewText"],
                "reviewed_at": r["date"]
            }
            for r in reviews
        ]
        if rows:
            saveReviews(rows)

        result = {"status": "completed", "reviews_ingested": len(rows), "completed_at": nowIso()}
    except ValueError as e:
        result = {"status": "failed", "error_message": str(e), "completed_at": nowIso()}
    except Exception as e:
        detail = "" if isinstance(e, requests.RequestException) else e
        logger.warning("Ingestion failed for target %s: %s: %s", targetId, type(e).__name__, detail)
        result = {
            "status": "failed",
            "error_message": "Could not fetch reviews from the review provider. Please try again.",
            "completed_at": nowIso()
        }

    updatedJob = supabaseClient.table("ingestion_jobs").update(result).eq("id", job["id"]).execute().data[0]
    if updatedJob["status"] == "failed":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=updatedJob["error_message"])
    return updatedJob

@app.post("/api/targets/{targetId}/ask")
def ask_review_question(targetId: str, request: QuestionRequest, userId: str = Depends(getCurrentUserId)):
    verifyTargetOwnership(targetId, userId)

    res = supabaseClient.table("reviews").select("review_text").eq("analysis_target_id", targetId).execute()
    reviews_data = res.data

    if not reviews_data:
        return {"answer": "No reviews have been ingested for this target at the moment. Please ingest data first before asking questions."}

    context_lines = [f"- {r.get('review_text')}" for r in reviews_data[:50] if r.get("review_text")]
    reviews_context = "\n".join(context_lines)

    if not reviews_context.strip():
         return {"answer": "The ingested reviews do not contain any text at the moment."}

    system_prompt = (
        "You are ReviewLens AI. Answer the user's question based strictly on the provided review evidence. "
        "If the reviews do not contain sufficient evidence to answer the question, clearly state that "
        "there is not enough information. Do not invent answers, guess, or use outside world knowledge. "
        "If the user asks about a different product, entity, or general knowledge, politely decline to answer."
    )

    apiKey = os.getenv("GEMINI_API_KEY")
    if not apiKey:
        logger.error("GEMINI_API_KEY is not set")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The AI assistant is not available right now.")

    prompt = f"Review Evidence:\n{reviews_context}\n\nUser Question: {request.question}"
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": prompt}]}]
    }

    try:
        response = requests.post(GEMINI_URL, headers={"x-goog-api-key": apiKey}, json=payload, timeout=15)
        response.raise_for_status()
        return {"answer": response.json()["candidates"][0]["content"]["parts"][0]["text"]}
    except requests.RequestException as e:
        # Log only the error type: the text of these errors can include request details.
        logger.warning("AI provider request failed: %s", type(e).__name__)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to connect to AI provider. Please try again.")
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.warning("Unexpected AI provider response: %s", type(e).__name__)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to process AI response.")

# Demo only: deliberately untested, to show the changed-code coverage gate failing.
def summarizeRatings(reviews):
    if not reviews:
        return {"count": 0, "average": None, "label": "No reviews"}

    average = round(sum(r["rating"] for r in reviews) / len(reviews), 1)

    if average >= 4:
        label = "Positive"
    elif average >= 3:
        label = "Mixed"
    else:
        label = "Negative"

    return {"count": len(reviews), "average": average, "label": label}