from app.target_repository import getReviewsForTarget, saveTarget, saveReview

class FakeQuery:
    """Minimal in-memory stand-in for the Supabase query builder."""

    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.newRow = None

    def insert(self, row):
        self.newRow = row
        return self

    def select(self, *_):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def execute(self):
        if self.newRow is not None:
            saved = {
                "id": f"id-{len(self.rows) + 1}",
                "created_at": "2026-10-31T12:00:00Z",
                **self.newRow,
            }
            self.rows.append(saved)

            class Result:
                data = [saved]

            return Result()

        matches = [r for r in self.rows if all(r.get(c) == v for c, v in self.filters)]

        class Result:
            data = matches

        return Result()

class FakeClient:
    def __init__(self):
        self.tables = {
            "analysis_targets": [],
            "reviews": []
        }

    def table(self, name):
        return FakeQuery(self.tables[name])



# test 1
# can we save a review and then retrieve it?
URL = "https://www.google.com/maps/place/test"

def test_review_is_persisted():
    client = FakeClient()

    target = saveTarget(client, "user_A", "place123", "Chipotle", URL)

    review = {
        "reviewId": "review123",
        "rating": 5,
        "reviewText": "Great food",
        "date": "2026-11-01T12:00:00Z"
    }

    saved = saveReview(client, target["id"], review)

    assert saved["analysis_target_id"] == target["id"]
    assert saved["rating"] == 5
    assert saved["review_text"] == "Great food"


# test 2
# will grabbing the reviews of an analysis target return ONLY its reviews, and not other targets' reviews?
def test_reviews_stay_with_correct_target():
    client = FakeClient()

    targetA = saveTarget(client, "user_A", "placeA", "Chipotle A", URL)
    targetB = saveTarget(client, "user_A", "placeB", "Chipotle B", URL)

    saveReview(client, targetA["id"], {
        "reviewId": "reviewA",
        "rating": 5,
        "reviewText": "Review A",
        "date": None
    })

    saveReview(client, targetB["id"], {
        "reviewId": "reviewB",
        "rating": 3,
        "reviewText": "Review B",
        "date": None
    })

    reviews = getReviewsForTarget(client, targetA["id"], "user_A")

    assert len(reviews) == 1
    assert reviews[0]["review_text"] == "Review A"


# test 3
# can user B get the reviews of user A's target? should not be able to.
def test_user_cannot_get_another_users_reviews():
    client = FakeClient()

    target = saveTarget(client, "user_A", "place123", "Chipotle", URL)

    saveReview(client, target["id"], {
        "reviewId": "review123",
        "rating": 5,
        "reviewText": "Great food",
        "date": None
    })

    reviews = getReviewsForTarget(client, target["id"], "user_B")

    assert reviews is None