"""Save As (S3-003): make a separate analysis from an existing one.

What the copy gets
  - a new id, a new name, and the same owner, place, platform and source link
  - its own copy of every stored review (new review ids)
  - its own completed ingestion record with the same counts and dates, so it shows the
    same ingestion state as the original

What the copy does NOT get
  - Q&A history. The copy starts with an empty history. (One clear rule, stated in the UI.)

After the copy exists, nothing links it to the original. Every table row points at its own
analysis id, so renaming, deleting or refreshing one never touches the other.

If anything fails part way, the half-made copy is deleted (its reviews and jobs go with it
through ON DELETE CASCADE), so a failed Save As leaves nothing behind.
"""

PAGE_SIZE = 1000  # the database returns at most 1000 rows per request
INSERT_BATCH = 500
REVIEW_FIELDS = "google_review_id,rating,review_text,reviewed_at,ingested_at"


def readReviews(client, targetId):
    """Every stored review of one analysis, read in pages."""
    rows, offset = [], 0
    while True:
        page = (
            client.table("reviews")
            .select(REVIEW_FIELDS)
            .eq("analysis_target_id", targetId)
            .order("id")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
            .data
        )
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def copyTarget(client, source, ownerClerkId, name):
    """Create a new analysis named `name` from `source` (a row the owner was already verified
    for). Returns the new analysis row."""
    created = (
        client.table("analysis_targets")
        .insert(
            {
                "owner_clerk_id": ownerClerkId,
                "google_place_id": source["google_place_id"],
                "business_name": name,
                "platform": source["platform"],
                "source_url": source["source_url"],
            }
        )
        .execute()
        .data[0]
    )
    newId = created["id"]

    try:
        reviews = readReviews(client, source["id"])
        for start in range(0, len(reviews), INSERT_BATCH):
            batch = [{**r, "analysis_target_id": newId} for r in reviews[start : start + INSERT_BATCH]]
            client.table("reviews").insert(batch).execute()

        job = _currentJob(client, source)
        if job or reviews:
            return _copyIngestionState(client, source, newId, job, len(reviews))
        return created  # the original had no reviews yet, so the copy has none either
    except Exception:
        _removeQuietly(client, newId)
        raise


def _currentJob(client, source):
    jobId = source.get("current_ingestion_id")
    if not jobId:
        return None
    rows = client.table("ingestion_jobs").select("*").eq("id", jobId).execute().data
    return rows[0] if rows else None


def _copyIngestionState(client, source, newId, job, reviewCount):
    job = job or {}
    savedJob = (
        client.table("ingestion_jobs")
        .insert(
            {
                "analysis_target_id": newId,
                "status": "completed",
                "reviews_ingested": reviewCount,
                "reviews_skipped": job.get("reviews_skipped"),
                "started_at": job.get("started_at"),
                "completed_at": job.get("completed_at"),
            }
        )
        .execute()
        .data[0]
    )
    return (
        client.table("analysis_targets")
        .update({"current_ingestion_id": savedJob["id"], "current_ingestion_at": source.get("current_ingestion_at") or job.get("completed_at")})
        .eq("id", newId)
        .execute()
        .data[0]
    )


def _removeQuietly(client, newId):
    try:
        client.table("analysis_targets").delete().eq("id", newId).execute()
    except Exception:
        pass  # the original error is the one worth reporting
