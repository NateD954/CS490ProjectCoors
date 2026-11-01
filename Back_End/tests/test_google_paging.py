from services import google_reviews


def makePage(start, count, token=None):
    page = {"reviews": [{"review_id": str(i), "rating": 5, "snippet": "ok"} for i in range(start, start + count)]}
    if token:
        page["serpapi_pagination"] = {"next_page_token": token}
    return page


def fakeSerpApi(pages, failOnCall=None):
    calls = []

    def fake(dataId, nextPageToken=None, sortBy=None, num=None):
        calls.append(nextPageToken)
        if failOnCall == len(calls):
            raise Exception("page failed")
        return pages[len(calls) - 1]

    return fake, calls


def test_single_page_without_token_stops(monkeypatch):
    fake, calls = fakeSerpApi([makePage(0, 5)])
    monkeypatch.setattr(google_reviews, "getGooglePlaceData", fake)

    data = google_reviews.getAllGooglePlaceData("0x1:0x2")

    assert len(data["reviews"]) == 5
    assert len(calls) == 1


def test_follows_tokens_and_stops_at_the_limit(monkeypatch):
    pages = [makePage(0, 10, "a"), makePage(10, 20, "b"), makePage(30, 20, "c"), makePage(50, 20, "d")]
    fake, calls = fakeSerpApi(pages)
    monkeypatch.setattr(google_reviews, "getGooglePlaceData", fake)

    data = google_reviews.getAllGooglePlaceData("0x1:0x2", maxReviews=50)

    assert len(data["reviews"]) == 50
    assert len(calls) == 3  # no fourth request once 50 are collected


def test_duplicate_reviews_are_removed(monkeypatch):
    fake, calls = fakeSerpApi([makePage(0, 5, "a"), makePage(3, 5)])
    monkeypatch.setattr(google_reviews, "getGooglePlaceData", fake)

    data = google_reviews.getAllGooglePlaceData("0x1:0x2")

    assert len(data["reviews"]) == 8


def test_a_failed_later_page_keeps_earlier_reviews(monkeypatch):
    fake, calls = fakeSerpApi([makePage(0, 5, "a")], failOnCall=2)
    monkeypatch.setattr(google_reviews, "getGooglePlaceData", fake)

    data = google_reviews.getAllGooglePlaceData("0x1:0x2")

    assert len(data["reviews"]) == 5


def test_reviews_without_text_do_not_count_toward_the_limit(monkeypatch):
    noText = {"reviews": [{"review_id": f"n{i}", "rating": 5} for i in range(10)], "serpapi_pagination": {"next_page_token": "a"}}
    withText = makePage(0, 10)
    fake, calls = fakeSerpApi([noText, withText])
    monkeypatch.setattr(google_reviews, "getGooglePlaceData", fake)

    data = google_reviews.getAllGooglePlaceData("0x1:0x2", maxReviews=50)

    assert len(data["reviews"]) == 10  # only the ones with text
    assert len(calls) == 2
