import requests
import json

POSTAL_CODE = "T3M1M9"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://flipp.com/"
}

def debug():
    print(f"🔎 finding active flyers for {POSTAL_CODE}...")
    res = requests.get("https://backflipp.wishabi.com/flipp/flyers", 
                       params={'postal_code': POSTAL_CODE, 'locale': 'en-ca'}, 
                       headers=HEADERS)
    flyers = res.json().get('flyers', [])

    # Pick a Grocery Store (Superstore)
    target = next((f for f in flyers if "Superstore" in f.get('merchant', '')), None)
    
    if target:
        print(f"\n--- INSPECTING: {target['merchant']} ---")
        url = f"https://backflipp.wishabi.com/flipp/flyers/{target['id']}"
        res = requests.get(url, headers=HEADERS)
        data = res.json()
        items = data.get('items') or data.get('spread_items') or []
        
        if items:
            print(f"✅ Found {len(items)} items.")
            print("Dumping raw data for the FIRST item:")
            first_item = items[0]
            # Print keys and values to find the hidden price
            print(json.dumps(first_item, indent=4))
        else:
            print("❌ No items found in this flyer.")

if __name__ == "__main__":
    debug()