import json
import logging
import requests
import argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

SERPER_API_KEY = "2b4655abae45e420e17ddeddc1670d60b79a9d11"
URL = "https://google.serper.dev/search"

def search_serper(query: str) -> dict:
    payload = json.dumps({"q": query})
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    
    logging.info(f"Querying Serper.dev for: '{query}'")
    response = requests.request("POST", URL, headers=headers, data=payload)
    
    if response.status_code == 200:
        return response.json()
    else:
        logging.error(f"Error {response.status_code}: {response.text}")
        return {}

def main():
    queries = [
        "ATP tennis matches today",
        "LaLiga matches today"
    ]
    
    results = {}
    for q in queries:
        data = search_serper(q)
        results[q] = data
        
    with open("serper_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    logging.info("Dumped Serper.dev results to serper_results.json")

if __name__ == "__main__":
    main()