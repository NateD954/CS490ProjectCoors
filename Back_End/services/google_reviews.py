import os
import requests
import re

def getGoogleDataIdFromURL(url):
    pattern = r"0x[0-9a-fA-F]+:0x[0-9a-fA-F]+" # regex pattern to grab the data_id
    dataId = re.search(pattern, url)
    if dataId:
        return dataId.group()


def getGooglePlaceData(dataId):
    apiKey = os.getenv('SERPAPI_API_KEY')
    
    # parameters for the API request
    searchParams = {     
        "engine": "google_maps_reviews",
        "data_id": dataId,
        "api_key": apiKey,
        "num": 20,
    }

    allReviews = []

    # send the API request and get the response in json
    while True:
        # set a limit of 50 reviews to avoid rate-limiting
        # yes it can go to 60 because 50 isn't a multiple of 20
        if len(allReviews) >= 50:
            break 
        response = requests.get("https://serpapi.com/search.json", params=searchParams)
        response.raise_for_status()
        data = response.json()

        print("page reviews:", len(data.get("reviews", [])))
        print("pagination:", data.get("serpapi_pagination"))

        if data.get("error"):
            raise Exception(f"Error from SerpAPI: {data['error']}")

        allReviews.extend(data.get("reviews", []))
        nextPageToken = data.get("serpapi_pagination", {}).get("next_page_token")

        if not nextPageToken:
            break

        searchParams["next_page_token"] = nextPageToken

    data["reviews"] = allReviews
    return data


# accepts json data from getGooglePlaceData
# returns a list of reviews with author, rating, and review text
def extractReviews(data):
    reviews = []
    for review in data.get("reviews", []):
        # check for malformed review data
        reviewText = review.get("snippet")
        rating = review.get("rating")
        if not reviewText:
            continue
        if rating not in [1, 2, 3, 4, 5]:
            continue


        reviews.append({
            "reviewId": review.get("review_id"),
            "rating": review.get("rating"),
            "reviewText": review.get("snippet"),
            "author": review.get("user", {}).get("name"),
            "date":   review.get("iso_date"),
            "url":    review.get("link")
        })
    return reviews