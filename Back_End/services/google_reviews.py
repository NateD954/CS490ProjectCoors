import os
import requests

def getGooglePlaceData(placeId):
    apiKey = os.getenv('SERPAPI_API_KEY')
   
    # parameters for the API request
    searchParams = {     
        "engine": "google_maps_reviews",
        "place_id": placeId,
        "api_key": apiKey
    }

    # send the API request and get the response in json
    response = requests.get("https://serpapi.com/search.json", params=searchParams)
    response.raise_for_status()
    response = response.json()

    # serpAPI sends back an "error" field if there's an error
    if response.get("error"):
        raise Exception(f"Error from SerpAPI: {response['error']}")
    
    return response

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