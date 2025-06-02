import requests

JSEARCH_API_KEY = "46b16dd206mshb3d738361ceccadp152accjsnfe223795ee27"  # Replace with your actual key
JSEARCH_API_URL = "https://jsearch.p.rapidapi.com/search"

querystring = {"query": "AI jobs in Bangalore", "num_pages": "1"}

headers = {
    "X-RapidAPI-Key": JSEARCH_API_KEY,
    "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
}

response = requests.get(JSEARCH_API_URL, headers=headers, params=querystring)

print(response.json())  # Check the actual API response
