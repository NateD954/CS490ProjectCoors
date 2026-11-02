from services.google_reviews import extractReviews

def test_extract_reviews():
    fakeData = {
        "reviews": [
            {
                "author_name": "Bob",
                "rating": 5,
                "review_text": "This is one of the places of all time."
            }
        ]
    }

    reviews = extractReviews(fakeData)

    assert reviews[0]["author"] == "Bob"
    assert reviews[0]["rating"] == 5
    assert reviews[0]["reviewText"] == "This is one of the places of all time."


def test_valid_review():
    fakeData = {
        "reviews": [
            {
                "review_id": "123",
                "rating": 5,
                "review_text": "Great place",
                "author_name": "Bob",
                "review_datetime_utc": "2026-10-28",
                "review_link": "example.com"
            }
        ]
    }

    reviews = extractReviews(fakeData)

    assert len(reviews) == 1
    assert reviews[0]["rating"] == 5
    assert reviews[0]["reviewText"] == "Great place"


# should skip reviews without review text
def test_missing_text():
    fakeData = {
        "reviews": [
            {
                "rating": 5
            }
        ]
    }

    reviews = extractReviews(fakeData)

# should skip reviews with an invalid rating
def test_invalid_rating():
    fakeData = {
        "reviews": [
            {
                "rating": 6,
                "review_text": "Great place"
            }
        ]
    }

    reviews = extractReviews(fakeData)

    assert len(reviews) == 0


# optional fields can be missing (pretty much everything except rating and review text)
def test_missing_optional_fields():
    fakeData = {
        "reviews": [
            {
                "rating": 5,
                "review_text": "Great place"
            }
        ]
    }

    reviews = extractReviews(fakeData)

    assert len(reviews) == 1
    assert reviews[0]["author"] is None
    assert reviews[0]["reviewId"] is None
    assert reviews[0]["date"] is None
    assert reviews[0]["url"] is None

    assert len(reviews) == 1