import os
import requests
import re
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()

def getGoogleDataIdFromURL(url):
    pattern = r"0x[0-9a-fA-F]+:0x[0-9a-fA-F]+" # regex pattern to grab the data_id
    dataId = re.search(pattern, url)
    if dataId:
        return dataId.group()


def getGooglePlaceData(dataId):
    apiKey = os.getenv("OPENWEBNINJA_API_KEY") or os.getenv("X-API-Key")
    
    searchParams = {
        "business_id": dataId,
        "limit": 25
    }

    response = requests.get(
        "https://api.openwebninja.com/local-business-data/business-reviews-v2",
        headers={"x-api-key": apiKey},
        params=searchParams,
        timeout=45
    )

    response.raise_for_status()
    data = response.json()

    if data.get("status") != "OK":
        raise Exception("Error from OpenWeb Ninja")

    return data["data"]


def parseReviews(data):
    """Return usable reviews and the number of source records skipped."""
    sourceReviews = data.get("reviews") if isinstance(data, dict) else None
    if not isinstance(sourceReviews, list):
        raise TypeError("Expected a list of reviews from the review provider.")

    reviews = []
    seenIds = set()

    for review in sourceReviews:
        if not isinstance(review, dict):
            continue
        reviewText = review.get("review_text")
        rating = review.get("rating")
        reviewId = review.get("review_id")
        date = review.get("review_datetime_utc")

        if not isinstance(reviewText, str) or not reviewText.strip() or "\x00" in reviewText:
            continue
        if isinstance(rating, bool) or rating not in (1, 2, 3, 4, 5):
            continue
        if reviewId is not None:
            if not isinstance(reviewId, str) or "\x00" in reviewId:
                continue
            reviewId = reviewId.strip() or None
            if reviewId is not None and reviewId in seenIds:
                continue
        try:
            if date is not None:
                parsed = datetime.fromisoformat(date)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                date = parsed.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            continue

        reviews.append({
            "reviewId": reviewId,
            "rating": rating,
            "reviewText": reviewText,
            "author": review.get("author_name"),
            "date": date,
            "url": review.get("review_link")
        })
        if reviewId is not None:
            seenIds.add(reviewId)

    return reviews, len(sourceReviews) - len(reviews)


def extractReviews(data):
    reviews, _ = parseReviews(data)
    return reviews


# test with https://www.google.com/maps/place/Chipotle+Mexican+Grill/@40.891156,-74.1109263,12z/data=!4m10!1m2!2m1!1schipotle!3m6!1s0x89c2fa2bfb0d27d5:0xcceef158b20fbf10!8m2!3d40.8911136!4d-74.0719572!15sCghjaGlwb3RsZSIDiAEBWgoiCGNoaXBvdGxlkgEUZmFzdF9mb29kX3Jlc3RhdXJhbnSaASNDaFpEU1VoTk1HOW5TMFZKUTBGblNVTmtORXBsZVV4UkVBReABAPoBBAgAEDE!16s%2Fg%2F11b70dhqcf?entry=ttu&g_ep=EgoyMDI2MTAyOC4wIKXMDSoASAFQAw%3D%3D
if __name__ == "__main__":
    url = "https://www.google.com/maps/place/Chipotle+Mexican+Grill/@40.891156,-74.1109263,12z/data=!4m10!1m2!2m1!1schipotle!3m6!1s0x89c2fa2bfb0d27d5:0xcceef158b20fbf10!8m2!3d40.8911136!4d-74.0719572!15sCghjaGlwb3RsZSIDiAEBWgoiCGNoaXBvdGxlkgEUZmFzdF9mb29kX3Jlc3RhdXJhbnSaASNDaFpEU1VoTk1HOW5TMFZKUTBGblNVTmtORXBsZVV4UkVBReABAPoBBAgAEDE!16s%2Fg%2F11b70dhqcf?entry=ttu&g_ep=EgoyMDI2MTAyOC4wIKXMDSoASAFQAw%3D%3D"
    dataId = getGoogleDataIdFromURL(url)
    data = getGooglePlaceData(dataId)
    reviews = extractReviews(data)

    print(len(reviews))
