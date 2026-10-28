from services.google_reviews import extractReviews

def test_extract_reviews():
    fakeData = {
        "reviews": [
            {
                "user": {"name": "Bob"},
                "rating": 5,
                "snippet": "This is one of the places of all time."
            }
        ]
    }

    reviews = extractReviews(fakeData)

    assert reviews[0]["author"] == "Bob"
    assert reviews[0]["rating"] == 5
    assert reviews[0]["review"] == "This is one of the places of all time."