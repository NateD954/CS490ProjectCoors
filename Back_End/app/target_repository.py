"""Database access for analysis_targets (S1-014).

Column names match Database/schema.sql. The Supabase client is passed in so
tests can supply a fake instead of a real database.
"""

TABLE = "analysis_targets"


def saveTarget(client, ownerClerkId, googlePlaceId, businessName, sourceUrl):
    """Insert one target. ownerClerkId must come from the verified Clerk token."""
    row = {
        "owner_clerk_id": ownerClerkId,
        "google_place_id": googlePlaceId,
        "business_name": businessName,
        "platform": "GOOGLE_MAPS",
        "source_url": sourceUrl,
    }
    res = client.table(TABLE).insert(row).execute()
    return res.data[0]


def getTargetForOwner(client, targetId, ownerClerkId):
    """Fetch a target only if the given owner owns it. Returns None otherwise."""
    res = (
        client.table(TABLE)
        .select("*")
        .eq("id", targetId)
        .eq("owner_clerk_id", ownerClerkId)
        .execute()
    )
    return res.data[0] if res.data else None


def saveReview(client, targetId, review):
    """Insert one review for a given target."""
    row = {
        "analysis_target_id": targetId,
        "google_review_id": review["reviewId"],
        "rating": review["rating"],
        "review_text": review["reviewText"],
        "reviewed_at": review["date"],
    }
    res = client.table("reviews").insert(row).execute()
    return res.data[0]


# fetch all reviews for a given target, but only if the given owner owns it
def getReviewsForTarget(client, targetId, ownerClerkId):
    target = getTargetForOwner(client, targetId, ownerClerkId)

    if target is None:
        return None

    res = (
        client.table("reviews")
        .select("*")
        .eq("analysis_target_id", targetId)
        .execute()
    )

    return res.data