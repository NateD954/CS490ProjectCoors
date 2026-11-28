"""Rename an analysis (S3-002).

Only the name shown to the user changes. The source URL, place id, reviews, ingestion
history and Q&A history are never written here.
"""

TABLE = "analysis_targets"


def updateTargetName(client, targetId, ownerClerkId, name):
    """Set business_name on one target owned by ownerClerkId. Returns the updated row, or
    None if no such target exists for that owner. Nothing else is written."""
    res = (
        client.table(TABLE)
        .update({"business_name": name})
        .eq("id", targetId)
        .eq("owner_clerk_id", ownerClerkId)
        .execute()
    )
    return res.data[0] if res.data else None
