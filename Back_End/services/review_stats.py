"""TEMPORARY demo file for the S2-001 changed-code coverage gate.

It exists only on a throwaway branch to show that the gate fails when new behavior is
added without tests. Do NOT merge it. Close the pull request and delete the branch.
"""


def summarizeRatings(ratings):
    """Count each star rating and describe the overall mood of a list of ratings."""
    counts = {star: 0 for star in (1, 2, 3, 4, 5)}
    for rating in ratings:
        if rating not in counts:
            raise ValueError(f"Rating must be 1 to 5, got {rating!r}")
        counts[rating] += 1

    total = sum(counts.values())
    if total == 0:
        return {"counts": counts, "total": 0, "average": None, "percentPositive": None, "mood": "no ratings"}

    average = round(sum(star * n for star, n in counts.items()) / total, 2)
    positive = counts[4] + counts[5]
    percentPositive = round(100 * positive / total, 1)

    if percentPositive >= 70:
        mood = "mostly positive"
    elif percentPositive <= 30:
        mood = "mostly negative"
    else:
        mood = "mixed"

    return {
        "counts": counts,
        "total": total,
        "average": average,
        "percentPositive": percentPositive,
        "mood": mood,
    }
