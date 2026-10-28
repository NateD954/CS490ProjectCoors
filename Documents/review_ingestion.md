# Review Ingestion

The review ingestion service uses SerpAPI to fetch JSON data of Google Place reviews.

# Input 

The function takes in a Google Maps place ID (which is also provided by SerpAPI).
The service itself doesn't provide a usable place ID, so you'll have to grab that before putting it here.

# Process

1. Call the 'getGooglePlaceData' function with the place ID argument.  
2. This function uses SerpAPI and returns the review data in JSON.  
3. Put this data into the 'extractReviews' function.
4. This function returns an array of each review's author, rating, and review text.

# Error Handling

'raise_for_status()' throws all HTTP errors from the 'getGooglePlaceData' request.  
SerpAPI also returns an 'error' field in their JSON response if there was an issue with the search itself; 'getGooglePlaceData' handles this and throws the error.