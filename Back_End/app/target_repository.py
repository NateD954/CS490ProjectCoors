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
