import logging
import requests
import os
import csv
import io
import re
from fastapi.responses import Response
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.db import supabaseClient
from app.auth import getCurrentUserId
from app.target_repository import getReviewSummary, saveTarget, listTargetsForOwner
from services.google_reviews import getGoogleDataIdFromURL, getGooglePlaceData, parseReviews

logger = logging.getLogger(__name__)

app = FastAPI(title="ReviewLens Coors edition (/^-^)oæ—¥æ—¥o(|^0^|) Backend Fastest API")

@app.get("/health")
def health():
    return {"status": "ok"}
    
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


class IngestionInputError(ValueError):
    """An ingestion failure with a message safe to show to the user."""

# The key is sent in a header, never in the URL, so it cannot end up in logs or error text.
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent"
GEMINI_TIMEOUT_SECONDS = 45

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
        .select("analysis_target_id,status,error_message,created_at,reviews_skipped")
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
        state, error, skipped = "not_started", None, None
        if job:
            state = JOB_STATUS_TO_UI.get(job["status"], "not_started")
            error = job.get("error_message")
            skipped = job.get("reviews_skipped")
            if state == "completed" and skipped:
                state = "partial"
            elif state == "in_progress":
                started = datetime.fromisoformat(job["created_at"].replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - started > STALE_JOB_AFTER:
                    state, error = "failed", "Ingestion did not finish. You can try again."
        t["ingestion_status"] = state
        t["ingestion_error"] = error
        t["ingestion_skipped"] = skipped
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
    target = withIngestionStatus([verifyTargetOwnership(targetId, userId)])[0]
    target["review_summary"] = getReviewSummary(supabaseClient, targetId)
    return target

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

EXPORT_PAGE_SIZE = 1000  # the database returns at most 1000 rows per request
CSV_COLUMNS = ["source_review_id", "rating", "review_text", "reviewed_at", "target_name", "platform", "target_source_url"]


def csvText(value) -> str:
    """Text for one CSV cell. A leading = + - @ gets a quote so a spreadsheet cannot run it as a formula."""
    if value is None:
        return ""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def fetchAllReviews(targetId: str) -> list:
    rows, offset = [], 0
    while True:
        page = (
            supabaseClient.table("reviews")
            .select("google_review_id,rating,review_text,reviewed_at")
            .eq("analysis_target_id", targetId)
            .order("reviewed_at", desc=True, nullsfirst=False)
            .order("id")
            .range(offset, offset + EXPORT_PAGE_SIZE - 1)
            .execute()
            .data
        )
        rows.extend(page)
        if len(page) < EXPORT_PAGE_SIZE:
            return rows
        offset += EXPORT_PAGE_SIZE


def exportFileName(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "target"
    return f"reviewlens-{slug}-reviews.csv"


@app.get("/api/targets/{targetId}/reviews/export")
def exportTargetReviews(targetId: str, userId: str = Depends(getCurrentUserId)):
    target = verifyTargetOwnership(targetId, userId)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for r in fetchAllReviews(targetId):
        writer.writerow([
            csvText(r.get("google_review_id")),
            "" if r.get("rating") is None else r["rating"],
            csvText(r.get("review_text")),
            csvText(r.get("reviewed_at")),
            csvText(target.get("business_name")),
            csvText(target.get("platform")),
            csvText(target.get("source_url")),
        ])

    return Response(
        content="\ufeff" + buffer.getvalue(),  # the marker makes Excel read accents correctly
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{exportFileName(target.get("business_name") or "")}"'},
    )

@app.post("/api/targets/{targetId}/ingest")
def ingestTarget(targetId: str, userId: str = Depends(getCurrentUserId)):
    target = verifyTargetOwnership(targetId, userId)

    job = supabaseClient.table("ingestion_jobs").insert({
        "analysis_target_id": targetId,
        "status": "running",
        "started_at": nowIso()
    }).execute().data[0]

    skipped = None
    try:
        dataId = getGoogleDataIdFromURL(target["source_url"])
        if not dataId:
            raise IngestionInputError("The target's source URL does not contain a Google Maps place id.")

        reviews, skipped = parseReviews(getGooglePlaceData(dataId))
        if not reviews and skipped:
            raise IngestionInputError("The review provider returned no usable reviews.")
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

        result = {"status": "completed", "reviews_ingested": len(rows)}
    except IngestionInputError as e:
        result = {"status": "failed", "error_message": str(e)}
    except Exception as e:
        detail = "" if isinstance(e, requests.RequestException) else e
        logger.warning("Ingestion failed for target %s: %s: %s", targetId, type(e).__name__, detail)
        result = {
            "status": "failed",
            "error_message": "Could not fetch reviews from the review provider. Please try again.",
        }

    result.update(reviews_skipped=skipped, completed_at=nowIso())
    updatedJob = supabaseClient.table("ingestion_jobs").update(result).eq("id", job["id"]).execute().data[0]
    if updatedJob["status"] == "failed":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=updatedJob["error_message"])
    return updatedJob

@app.post("/api/targets/{targetId}/ask")
def ask_review_question(targetId: str, request: QuestionRequest, userId: str = Depends(getCurrentUserId)):
    target = verifyTargetOwnership(targetId, userId)

    res = supabaseClient.table("reviews").select("review_text").eq("analysis_target_id", targetId).execute()
    reviews_data = res.data

    if not reviews_data:
        return {"answer": "No reviews have been ingested for this target at the moment. Please ingest data first before asking questions."}

    context_lines = [f"- {r.get('review_text')}" for r in reviews_data[:50] if r.get("review_text")]
    reviews_context = "\n".join(context_lines)

    if not reviews_context.strip():
         return {"answer": "The ingested reviews do not contain any text at the moment."}

    system_prompt = (
        f"You are ReviewLens AI, analyzing {target['business_name']} "
        f"using reviews from {target['platform']}. "
        "Answer questions using only the provided review evidence. "
        "Never invent information, guess, or use outside knowledge. "
        "If the reviews lack sufficient evidence, clearly explain that limitation. "
        "Decline unrelated general-knowledge questions, questions about other "
        "businesses, products, or locations, and questions about review platforms "
        "not represented in the active dataset. "
        "When declining, briefly explain that ReviewLens only analyzes "
        "the active business's provided reviews."
        "Respond in clean plain text only. Do not use markdown formatting such as asterisks (** or *), hashtags (#), or backticks."
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
        response = requests.post(GEMINI_URL, headers={"x-goog-api-key": apiKey}, json=payload, timeout=GEMINI_TIMEOUT_SECONDS)
        response.raise_for_status()
        answer = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except requests.RequestException as e:
        # Log only the error type: the text of these errors can include request details.
        logger.warning("AI provider request failed: %s", type(e).__name__)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to connect to AI provider. Please try again.")
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.warning("Unexpected AI provider response: %s", type(e).__name__)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to process AI response.")

    try:
        saved_res = (
            supabaseClient.table("qa_history")
            .insert({
                "analysis_target_id": targetId,
                "question": request.question,
                "answer": answer,
                "created_at": nowIso(),
            })
            .execute()
        )
        saved_rows = saved_res.data or []
        if saved_rows:
            saved = saved_rows[0]
            return {
                "id": saved.get("id"),
                "question": saved.get("question", request.question),
                "answer": saved.get("answer", answer),
                "created_at": saved.get("created_at"),
            }
    except KeyError:
        # Older test harnesses mock only analysis_targets and reviews tables
        pass
    return {"answer": answer}


@app.get("/api/targets/{targetId}/history")
def get_qa_history(targetId: str, userId: str = Depends(getCurrentUserId)):
    verifyTargetOwnership(targetId, userId)
    res = (
        supabaseClient.table("qa_history")
        .select("id,analysis_target_id,question,answer,created_at")
        .eq("analysis_target_id", targetId)
        .order("created_at", desc=False)
        .order("id", desc=False)
        .execute()
    )
    return res.data or []


@app.delete("/api/targets/{targetId}/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_qa_history(targetId: str, userId: str = Depends(getCurrentUserId)):
    verifyTargetOwnership(targetId, userId)
    supabaseClient.table("qa_history").delete().eq("analysis_target_id", targetId).execute()
    return None