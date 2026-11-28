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
from uuid import UUID

from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from httpx import HTTPError
from postgrest.exceptions import APIError

from app.db import supabaseClient
from app.auth import getCurrentUserId
from app.target_repository import getReviewSummary, saveTarget, listTargetsForOwner
from app.analysis_export import analysisFileName, buildAnalysisMarkdown, slugify
from app.review_refresh import IngestionBusy, beginIngestion, completeIngestion, failIngestion
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

class ComparisonCreateRequest(BaseModel):
    name: str
    targetAId: UUID
    targetBId: UUID


class IngestionInputError(ValueError):
    """An ingestion failure with a message safe to show to the user."""

# The key is sent in a header, never in the URL, so it cannot end up in logs or error text.
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent"
GEMINI_TIMEOUT_SECONDS = 45

# S3-013: the model names the reviews behind its answer by tag, on a last line like "EVIDENCE: R2, R7".
# Only the tags are trusted. The review text and rating shown to the user are read from the database.
MAX_SUPPORTING_REVIEWS = 5
SUPPORTING_REVIEW_FIELDS = "id,rating,review_text,reviewed_at"
EVIDENCE_LINE = re.compile(r"^[ \t]*EVIDENCE:(.*)$", re.IGNORECASE | re.MULTILINE)


def supportingReview(row: dict) -> dict:
    return {field: row.get(field) for field in SUPPORTING_REVIEW_FIELDS.split(",")}


def splitAnswerAndEvidence(text: str, cited: dict) -> tuple:
    """Returns the answer without its EVIDENCE line, and the stored reviews that line names.
    `cited` maps each tag number sent to the model to its review row. Tags that were not sent
    in this request (invented, or from another target) match nothing and are dropped."""
    lines = EVIDENCE_LINE.findall(text)
    if not lines:
        return text, []
    reviews = []
    for number in re.findall(r"\bR(\d+)\b", lines[-1]):
        review = cited.get(int(number))
        if review and review.get("id") and review not in reviews:
            reviews.append(review)
    return EVIDENCE_LINE.sub("", text).strip(), [supportingReview(r) for r in reviews[:MAX_SUPPORTING_REVIEWS]]

JOB_STATUS_TO_UI = {"pending": "in_progress", "running": "in_progress", "completed": "completed", "failed": "failed"}
STALE_JOB_AFTER = timedelta(minutes=10)

def withIngestionStatus(targets: list) -> list:
    if not targets:
        return targets
    ids = [t["id"] for t in targets]
    jobs = (
        supabaseClient.table("ingestion_jobs")
        .select("id,analysis_target_id,status,error_message,created_at,started_at,reviews_skipped")
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
                started = datetime.fromisoformat((job.get("started_at") or job["created_at"]).replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - started > STALE_JOB_AFTER:
                    state, error = "failed", "Ingestion did not finish. You can try again."
        t["ingestion_status"] = state
        t["ingestion_error"] = error
        t["ingestion_skipped"] = skipped
        t["ingestion_id"] = job.get("id") if job else None
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
CSV_COLUMNS = [
    "source_review_id", "rating", "review_text", "reviewed_at",
    "target_name", "platform", "target_source_url", "exported_at",
]


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
    return f"reviewlens-{slugify(name)}-reviews.csv"


@app.get("/api/targets/{targetId}/reviews/export")
def exportTargetReviews(targetId: str, userId: str = Depends(getCurrentUserId)):
    target = verifyTargetOwnership(targetId, userId)

    # S3-019: every row carries the time of the export, so a file found later can be dated.
    exportedAt = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
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
            exportedAt,
        ])

    return Response(
        content="\ufeff" + buffer.getvalue(),  # the marker makes Excel read accents correctly
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{exportFileName(target.get("business_name") or "")}"'},
    )

@app.get("/api/targets/{targetId}/export/markdown")
def exportTargetAnalysis(targetId: str, userId: str = Depends(getCurrentUserId)):
    """S3-018: the saved analysis (details, ingestion summary, Q&A history) as a Markdown file."""
    # Ownership is checked first, so nothing else is read for a user who does not own the target.
    target = withIngestionStatus([verifyTargetOwnership(targetId, userId)])[0]
    summary = getReviewSummary(supabaseClient, targetId)
    history = (
        supabaseClient.table("qa_history")
        .select("id,question,answer,created_at")
        .eq("analysis_target_id", targetId)
        .order("created_at", desc=False)
        .order("id", desc=False)
        .execute()
        .data
        or []
    )

    markdown = buildAnalysisMarkdown(target, summary, history, datetime.now(timezone.utc))
    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{analysisFileName(target.get("business_name") or "")}"'},
    )

@app.post("/api/targets/{targetId}/ingest")
def ingestTarget(targetId: str, userId: str = Depends(getCurrentUserId)):
    target = verifyTargetOwnership(targetId, userId)

    try:
        job = beginIngestion(supabaseClient, targetId)
    except IngestionBusy as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    except Exception as error:
        logger.warning("Could not start ingestion: %s", type(error).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Could not start ingestion. Please try again.")

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
        return completeIngestion(supabaseClient, job, rows, skipped)
    except IngestionInputError as e:
        message = str(e)
    except Exception as e:
        logger.warning("Ingestion failed for target %s: %s", targetId, type(e).__name__)
        message = "Could not fetch reviews from the review provider. Please try again."

    try:
        updatedJob = failIngestion(supabaseClient, job, message, skipped)
    except Exception as error:
        logger.warning("Could not confirm ingestion state: %s", type(error).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Could not confirm ingestion status. Reload the target to check the latest run.")
    if updatedJob["status"] == "completed":
        return updatedJob
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=updatedJob.get("error_message") or message)

@app.post("/api/targets/{targetId}/ask")
def ask_review_question(targetId: str, request: QuestionRequest, userId: str = Depends(getCurrentUserId)):
    target = verifyTargetOwnership(targetId, userId)

    res = (
        supabaseClient.table("reviews").select(SUPPORTING_REVIEW_FIELDS)
        .eq("analysis_target_id", targetId)
        .order("ingested_at", desc=True).order("id")
        .execute()
    )
    reviews_data = res.data

    if not reviews_data:
        return {"answer": "No reviews have been ingested for this target at the moment. Please ingest data first before asking questions."}

    # Each review sent to the model gets a short tag, so the model can say which ones it used.
    cited = dict(enumerate((r for r in reviews_data[:50] if r.get("review_text")), start=1))
    context_lines = [f"- {r.get('review_text')} [R{number}]" for number, r in cited.items()]
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
        " Each review ends with a tag such as [R3]. After the answer, add one final line in the form "
        "'EVIDENCE: R2, R7' listing the tags of the two to five reviews that best support the answer. "
        "Use only tags that appear in the review evidence. If you decline the question or the reviews "
        "lack sufficient evidence, write 'EVIDENCE: none'. Do not mention the tags anywhere else."
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
        answer, supporting = splitAnswerAndEvidence(response.json()["candidates"][0]["content"]["parts"][0]["text"], cited)
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
                "supporting_review_ids": [r["id"] for r in supporting],
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
                "supporting_reviews": supporting,
            }
    except KeyError:
        # Older test harnesses mock only analysis_targets and reviews tables
        pass
    return {"answer": answer, "supporting_reviews": supporting} if supporting else {"answer": answer}


@app.get("/api/targets/{targetId}/history")
def get_qa_history(targetId: str, userId: str = Depends(getCurrentUserId)):
    verifyTargetOwnership(targetId, userId)
    res = (
        supabaseClient.table("qa_history")
        .select("id,analysis_target_id,question,answer,created_at,supporting_review_ids")
        .eq("analysis_target_id", targetId)
        .order("created_at", desc=False)
        .order("id", desc=False)
        .execute()
    )
    entries = res.data or []

    # S3-013: only review ids are saved with an answer. The reviews are read again here, limited
    # to this target, so an id from another target or a deleted review shows nothing.
    ids = sorted({i for e in entries for i in (e.get("supporting_review_ids") or [])})
    found = {}
    for start in range(0, len(ids), 100):
        rows = (
            supabaseClient.table("reviews")
            .select(SUPPORTING_REVIEW_FIELDS)
            .eq("analysis_target_id", targetId)
            .in_("id", ids[start:start + 100])
            .execute()
            .data
            or []
        )
        found.update({r["id"]: supportingReview(r) for r in rows})
    for e in entries:
        saved = (e.pop("supporting_review_ids", None) or [])[:MAX_SUPPORTING_REVIEWS]
        e["supporting_reviews"] = [found[i] for i in saved if i in found]
    return entries


@app.delete("/api/targets/{targetId}/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_qa_history(targetId: str, userId: str = Depends(getCurrentUserId)):
    verifyTargetOwnership(targetId, userId)
    supabaseClient.table("qa_history").delete().eq("analysis_target_id", targetId).execute()
    return None
@app.post("/api/comparisons", status_code=status.HTTP_201_CREATED)
def createComparison(body: ComparisonCreateRequest, userId: str = Depends(getCurrentUserId)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enter a name for the comparison.")
    if body.targetAId == body.targetBId:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose two different targets to compare.")

    targetAId = str(body.targetAId)
    targetBId = str(body.targetBId)
    verifyTargetOwnership(targetAId, userId)
    verifyTargetOwnership(targetBId, userId)

    row = {
        "owner_clerk_id": userId,
        "name": name,
        "target_a_id": targetAId,
        "target_b_id": targetBId,
    }
    return supabaseClient.table("comparisons").insert(row).execute().data[0]


def verifyComparisonOwnership(comparisonId: str, userId: str) -> dict:
    rows = supabaseClient.table("comparisons").select("*").eq("id", comparisonId).execute().data
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found.")
    if rows[0]["owner_clerk_id"] != userId:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this comparison.")
    return rows[0]


def comparisonDataset(targetId: Optional[str], userId: str) -> dict:
    unavailable = {"id": targetId, "unavailable": True, "reason": "unavailable"}
    if targetId is None:
        return unavailable
    try:
        target = withIngestionStatus([verifyTargetOwnership(targetId, userId)])[0]
        summary = getReviewSummary(supabaseClient, targetId)
        reviews = (
            supabaseClient.table("reviews")
            .select("id,rating,review_text,reviewed_at")
            .eq("analysis_target_id", targetId)
            .order("reviewed_at", desc=True, nullsfirst=False)
            .order("id")
            .limit(3)
            .execute().data
        )
        return {
            "id": targetId,
            "unavailable": False,
            "business_name": target["business_name"],
            "platform": target["platform"],
            "source_url": target["source_url"],
            "review_summary": summary,
            "ingestion_status": target["ingestion_status"],
            "ingestion_error": target["ingestion_error"],
            "ingestion_skipped": target["ingestion_skipped"],
            "sample_reviews": reviews,
        }
    except HTTPException as error:
        if error.status_code not in (403, 404):
            raise
        # saved links still need an ownership check
        return unavailable
    except (APIError, HTTPError) as error:
        logger.warning("Comparison dataset could not be loaded: %s", type(error).__name__)
        return {**unavailable, "reason": "temporarily_unavailable"}


@app.get("/api/comparisons")
def listComparisons(userId: str = Depends(getCurrentUserId)):
    rows, offset = [], 0
    while True:
        page = (
            supabaseClient.table("comparisons").select("*")
            .eq("owner_clerk_id", userId)
            .order("created_at", desc=True).order("id", desc=True)
            .range(offset, offset + 999)
            .execute().data
        )
        rows.extend(page)
        if len(page) < 1000:
            return rows
        offset += 1000


@app.get("/api/comparisons/{comparisonId}")
def getComparison(comparisonId: UUID, userId: str = Depends(getCurrentUserId)):
    comparison = verifyComparisonOwnership(str(comparisonId), userId)
    return {
        **comparison,
        "target_a": comparisonDataset(comparison["target_a_id"], userId),
        "target_b": comparisonDataset(comparison["target_b_id"], userId),
    }


@app.delete("/api/comparisons/{comparisonId}", status_code=status.HTTP_204_NO_CONTENT)
def deleteComparison(comparisonId: UUID, userId: str = Depends(getCurrentUserId)):
    verifyComparisonOwnership(str(comparisonId), userId)
    supabaseClient.table("comparisons").delete().eq("id", str(comparisonId)).eq("owner_clerk_id", userId).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
