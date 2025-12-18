import requests
import pandas as pd
import datetime
import os
import time
import re
from dotenv import load_dotenv
from sqlalchemy import create_engine
from classifier import categorize_groceries

# --- 1. CONFIGURATION & SECRETS ---
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

# Files
HISTORY_FILE = 'seton_grocery_history.csv' # The "Raw" Database (Input for cleaner)
DASHBOARD_FILE = 'clean_grocery_data.csv'  # The "Clean" Database (Output for dashboard)

# Scraper Settings
POSTAL_CODE = "T3M1M9"
STORES = [
    "Real Canadian Superstore", "Save-On-Foods", "Calgary Co-op",
    "Sobeys", "Safeway", "No Frills"
]

BASE_URL = "https://backflipp.wishabi.com/flipp"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://flipp.com/"
}

# --- 2. CLEANER CONFIGURATION (Category Mapping) ---
CATEGORY_MAP = {
    # Meat & Protein
    "Meat": "Meat & Protein", "Meat & Seafood": "Meat & Protein", 
    "Deli": "Meat & Protein", "Prepared Meals": "Meat & Protein", 
    "Seafood": "Meat & Protein", "Fish": "Meat & Protein",
    # Dairy & Fridge
    "Dairy": "Dairy & Fridge", "Dairy & Eggs": "Dairy & Fridge", 
    "Yogurt": "Dairy & Fridge", "Cheese": "Dairy & Fridge",
    "Milk": "Dairy & Fridge", "Butter": "Dairy & Fridge", "Frozen": "Dairy & Fridge", 
    # Produce
    "Produce": "Produce", "Fruit": "Produce", "Vegetables": "Produce",
    # Pantry
    "Pantry": "Pantry & Household", "Baking": "Pantry & Household", 
    "Baking Goods": "Pantry & Household", "Baked Goods": "Pantry & Household",
    "Meal Kits": "Pantry & Household", "Nuts & Seeds": "Pantry & Household",
    "Canned": "Pantry & Household", "Condiments": "Pantry & Household",
    # Snacks
    "Snacks": "Snacks & Treats", "Candy": "Snacks & Treats", 
    "Sweets": "Snacks & Treats", "Confectionery": "Snacks & Treats", 
    "Desserts": "Snacks & Treats", "Beverages": "Snacks & Treats",
    "Chips": "Snacks & Treats", "Cookies": "Snacks & Treats",
    # Health & Home
    "Health": "Health & Home", "Personal Care": "Health & Home", 
    "Pets": "Health & Home", "Baby": "Health & Home", 
    "Cleaning": "Health & Home", "Paper": "Health & Home"
}

# --- 3. HELPER FUNCTIONS ---
def get_active_flyers(postal_code):
    url = f"{BASE_URL}/flyers"
    params = {'postal_code': postal_code, 'locale': 'en-ca'}
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=15)
        return response.json().get('flyers', [])
    except:
        return []

def get_flyer_items(flyer_id):
    url = f"{BASE_URL}/flyers/{flyer_id}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            data = response.json()
            return data.get('items') or data.get('spread_items') or []
    except:
        pass
    return []

def clean_price(item_dict):
    keys = ['price', 'current_price', 'price_text', 'sale_price', 'original_price']
    raw_price = next((item_dict[k] for k in keys if item_dict.get(k)), None)
    if not raw_price: return None, None
    try:
        clean = str(raw_price).replace('$', '').replace('¢', '').lower().strip()
        multibuy = re.search(r'(\d+)\s*(?:/|for)\s*\$?(\d+(?:\.\d+)?)', clean)
        if multibuy:
            qty = float(multibuy.group(1))
            total_price = float(multibuy.group(2))
            if qty > 0: return raw_price, total_price / qty
        matches = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", clean)
        if matches: 
            return raw_price, float(matches[0])
        return raw_price, None
    except:
        return raw_price, None

def run_post_processing_cleaner():
    """
    This runs immediately after scraping to generate the 'clean' file for the dashboard.
    """
    print("\n--- 🧹 Running Cleaner Pipeline ---")
    if not os.path.exists(HISTORY_FILE):
        print(f"[!] Error: {HISTORY_FILE} not found to clean.")
        return

    # Load History
    df = pd.read_csv(HISTORY_FILE)
    
    # Rename Columns (Standardize for Dashboard)
    df = df.rename(columns={
        'Item': 'item', 'Store': 'store', 'Category': 'category',
        'Price_Value': 'price', 'Date': 'date', 'Sub_Category': 'sub_category',
        'Original_Price': 'original_price', 'Valid_Until': 'valid_until'
    })

    # Apply Mappings
    df['category'] = df['category'].astype(str).str.strip()
    df['display_category'] = df['category'].map(CATEGORY_MAP).fillna("Other")

    # Clean Sub-Category
    if 'sub_category' in df.columns:
        df['sub_category'] = df['sub_category'].fillna("General").astype(str).str.title()
    else:
        df['sub_category'] = "General"

    # Math: Savings
    df['price'] = pd.to_numeric(df['price'], errors='coerce')
    if 'original_price' in df.columns:
        df['original_price'] = pd.to_numeric(df['original_price'], errors='coerce')
        df['savings_pct'] = ((df['original_price'] - df['price']) / df['original_price']) * 100
        df['savings_pct'] = df['savings_pct'].fillna(0)
    else:
        df['savings_pct'] = 0

    # Save
    df.to_csv(DASHBOARD_FILE, index=False)
    print(f"✅ Dashboard Ready! Clean data saved to: {DASHBOARD_FILE}")

# --- 4. MAIN SCRAPER LOGIC ---
print(f">> Scanning flyers for {POSTAL_CODE}...")
flyers = get_active_flyers(POSTAL_CODE)
if not flyers:
    print("[!] No flyers found.")
    exit()

selected_flyers = []
for store in STORES:
    matches = [f for f in flyers if store.lower() in f.get('merchant', '').lower()]
    best = None
    for f in matches:
        if "weekly" in f.get('name', '').lower(): best = f; break
        if not best: best = f
    if best:
        selected_flyers.append(best)
        print(f"   + Selected: {best['merchant']}")

new_deals = []
print("\n>> Extracting items...")
for flyer in selected_flyers:
    items = get_flyer_items(flyer['id'])
    for item in items:
        name = item.get('name')
        price_txt, price_val = clean_price(item)
        if name:
            new_deals.append({
                'Date': datetime.date.today(),
                'Store': flyer['merchant'],
                'Original_Name': name,
                'Item': name, 
                'Price_Text': price_txt if price_txt else "Check Store",
                'Price_Value': price_val if price_val is not None else 0.0,
                'Valid_Until': item.get('valid_to') or flyer.get('valid_to')
            })

# --- 5. AI & CACHING ---
if new_deals:
    known_cache = {}
    if os.path.exists(HISTORY_FILE):
        try:
            df_hist = pd.read_csv(HISTORY_FILE)
            if 'Original_Name' in df_hist.columns:
                clean_cache = df_hist.drop_duplicates(subset=['Original_Name']).set_index('Original_Name')
                known_cache = clean_cache[['Item', 'Category']].to_dict('index')
        except: pass

    unique_names = list(set(d['Original_Name'] for d in new_deals))
    unknown_items = [name for name in unique_names if name not in known_cache]
    
    print(f"   Found {len(unique_names)} items ({len(unknown_items)} new for AI).")

    ai_results = []
    if unknown_items:
        batch_size = 100
        for i in range(0, len(unknown_items), batch_size):
            batch = unknown_items[i : i + batch_size]
            print(f"   ...AI Batch {i // batch_size + 1}/{len(unknown_items)//batch_size + 1}")
            try:
                ai_results.extend(categorize_groceries(batch))
            except Exception as e:
                print(f"   [!] Batch failed: {e}")

    for item in ai_results:
        known_cache[item.original_name] = {'Category': item.category, 'Item': item.clean_name}

    for deal in new_deals:
        original = deal['Original_Name']
        if original in known_cache:
            deal['Category'] = known_cache[original]['Category']
            deal['Item'] = known_cache[original]['Item']
            deal['Is_Deal'] = True
        else:
            deal['Category'] = "Uncategorized"
            deal['Is_Deal'] = False

    # --- SAVE HISTORY ---
    df_new = pd.DataFrame(new_deals)
    df_new['Item'] = df_new['Item'].astype(str).str.title()
    
    if os.path.exists(HISTORY_FILE):
        try:
            df_hist = pd.read_csv(HISTORY_FILE)
            df_combined = pd.concat([df_hist, df_new])
        except:
            df_combined = df_new
    else:
        df_combined = df_new
            
    df_combined.drop_duplicates(subset=['Store', 'Original_Name', 'Price_Text', 'Valid_Until'], inplace=True)
    df_combined.to_csv(HISTORY_FILE, index=False)
    print(f"\n>> History updated ({len(df_combined)} records).")

    # --- 6. TRIGGER CLEANER ---
    # This creates the clean file for the dashboard
    run_post_processing_cleaner()

else:
    print("[!] No items found.")