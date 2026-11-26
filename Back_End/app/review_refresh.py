from datetime import datetime, timezone


class IngestionBusy(RuntimeError):
    pass


def beginIngestion(client, targetId):
    try:
        return client.rpc("begin_review_ingestion", {"p_target_id": targetId}).execute().data[0]
    except Exception as error:
        if getattr(error, "code", None) == "55P03":
            raise IngestionBusy("Ingestion is already running for this target.") from error
        raise


def completeIngestion(client, job, rows, skipped):
    # the same job can be retried safely if the reply gets lost
    for attempt in range(2):
        try:
            return client.rpc("complete_review_ingestion", {
                "p_target_id": job["analysis_target_id"],
                "p_job_id": job["id"],
                "p_reviews": rows,
                "p_skipped": skipped,
            }).execute().data[0]
        except Exception:
            if attempt == 1:
                raise


def failIngestion(client, job, message, skipped):
    saved = client.table("ingestion_jobs").update({
        "status": "failed",
        "error_message": message,
        "reviews_skipped": skipped,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", job["id"]).eq("status", "running").execute().data
    if saved:
        return saved[0]
    # don't mark a committed refresh as failed after a lost reply
    return client.table("ingestion_jobs").select("*").eq("id", job["id"]).execute().data[0]
