import logging
import requests
import os
import google.generativeai as genai
from pydantic import BaseModel
from fastapi import HTTPException
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi.middleware.cors import CORSMiddleware
from app.db import supabaseClient
from fastapi import FastAPI, Depends, HTTPException, Query, status
from pydantic import BaseModel
from app.auth import getCurrentUserId
from app.target_repository import saveTarget, listTargetsForOwner
from services.google_reviews import getGoogleDataIdFromURL, getGooglePlaceData, extractReviews

logger = logging.getLogger(__name__)

app = FastAPI(title="ReviewLens Coors edition (/^-^)o日日o(|^0^|) Backend Fastest API")

if os.getenv("GEMINI_API_KEY"):
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
else:
    raise ValueError("GEMINI_API_KEY is not set")

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

class QuestionRequest(BaseModel):
    question: str

def saveReviews(rows: list) -> None:
    # The connection to Supabase can be dropped while the slow review fetch runs, so try once more.
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
    """Add the latest ingestion job's state to each target so the UI can display it."""
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
        latest.setdefault(job["analysis_target_id"], job)  # newest job comes first

    for t in targets:
        job = latest.get(t["id"])
        state, error = "not_started", None
        if job:
            state = JOB_STATUS_TO_UI.get(job["status"], "not_started")
            error = job.get("error_message")
            started = datetime.fromisoformat(job["created_at"].replace("Z", "+00:00"))
            # A job that never finished (for example the server stopped midway) must not block a retry.
            if state == "in_progress" and datetime.now(timezone.utc) - started > STALE_JOB_AFTER:
                state, error = "failed", "Ingestion did not finish. You can try again."
        t["ingestion_status"] = state
        t["ingestion_error"] = error
    return targets

def isGoogleUrl(url: str) -> bool:
    """True for an http(s) link whose host is google.com or one of its subdomains."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme in ("http", "https") and (host == "google.com" or host.endswith(".google.com"))

def nowIso() -> str:
    return datetime.now(timezone.utc).isoformat()

# Same shape FastAPI uses for its own 422s, so the frontend can show each message under its field.
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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=errors)

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
    # Newest first (reviews with no date last); id keeps the order stable between pages.
    query = (
        supabaseClient.table("reviews")
        .select("*")
        .eq("analysis_target_id", targetId)
        .order("reviewed_at", desc=True, nullsfirst=False)
        .order("id")
    )
    if limit is not None:  # without a limit, every review is returned as before
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
        # Don't pass the raw error on: requests errors include the URL, which contains the SerpAPI key.
        # requests errors include the URL (and the SerpAPI key), so only log their type.
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
    # 1. Verify user ownership
    verifyTargetOwnership(targetId, userId)
    
    # Fetch the targets from Supabase (S2-010)
    res = supabaseClient.table("reviews").select("review_text").eq("analysis_target_id", targetId).execute()
    reviews_data = res.data

    if not reviews_data:
        return {"answer": "No reviews have been ingested for this target at the moment. Please ingest data first before asking questions."}

    # Formatting
    context_lines = [f"- {r.get('review_text')}" for r in reviews_data[:50] if r.get("review_text")]
    reviews_context = "\n".join(context_lines)

    if not reviews_context.strip():
         return {"answer": "The ingested reviews do not contain any text at the moment."}

    # ReviewLens System Prompt default
    system_prompt = (
        "You are ReviewLens AI. Answer the user's question based strictly on the provided review evidence. "
        "If the reviews do not contain sufficient evidence to answer the question, clearly state that "
        "there is not enough information. Do not invent answers, guess, or use outside world knowledge. "
        "If the user asks about a different product, entity, or general knowledge, politely decline to answer."
    )

    # Initialize Gemini
    try:
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=system_prompt
        )
        
        prompt = f"Review Evidence:\n{reviews_context}\n\nUser Question: {request.question}"
        response = model.generate_content(prompt)
        
        return {"answer": response.text}
    except Exception as e:
        logger.error("Gemini API Error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to generate AI response. Please try again later.")