# Review Ingestion

The review ingestion service uses SerpAPI to fetch JSON data of Google Place reviews.

# Input 

The function takes in a Google Maps place ID (which is also provided by SerpAPI).
The service itself doesn't provide a usable place ID, so you'll have to grab that before putting it here.

# Process

1. Find a Google Maps place URL.
2. Input the URL into the 'getGoogleDataIdFromURL' function. This returns the data ID.
3. Call the 'getGooglePlaceData' function with the data ID argument.  
4. This function uses SerpAPI and returns the review data in JSON.  
5. Put this data into the 'extractReviews' function.
6. This function returns a list of dictionaries. Each dictionary holds a review's reviewId, rating, reviewText, author, date, and url fields.


# Notes

A valid review must have a rating and review text; the other fields are optional, and 'extractReviews' will still return them. If a review doesn't have a rating or review text, it won't be returned in the list. 

# Error Handling

'raise_for_status()' throws all HTTP errors from the 'getGooglePlaceData' request.  
SerpAPI also returns an 'error' field in their JSON response if there was an issue with the search itself; 'getGooglePlaceData' handles this and throws the error.