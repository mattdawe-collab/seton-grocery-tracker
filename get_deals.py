import requests
import pandas as pd
import datetime
import os
import time
import re
from dotenv import load_dotenv
from sqlalchemy import create_engine
from classifier import categorize_groceries

# --- 1. SECURELY LOAD SECRETS ---
# Explicitly look for .env in the current folder to avoid path issues
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

# DEBUG: Check if key exists (Prints "Found" or "Missing" without revealing the password)
db_pass_check = os.environ.get("SUPABASE_DB_PASS")
print(f">> System Check: Supabase Password is {'[FOUND]' if db_pass_check else '[MISSING - Check .env file]'}")

# --- CONFIGURATION ---
POSTAL_CODE = "T3M1M9"
STORES = [
    "Real Canadian Superstore",
    "Save-On-Foods",
    "Calgary Co-op",
    "Sobeys",
    "Safeway",
    "No Frills"
]

BASE_URL = "https://backflipp.wishabi.com/flipp"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://flipp.com/"
}

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
        
        # FIX: Handle "2 for $5" or "2/$5" logic
        # Matches: "2/$5", "2 / $5", "2 for 5"
        multibuy = re.search(r'(\d+)\s*(?:/|for)\s*\$?(\d+(?:\.\d+)?)', clean)
        if multibuy:
            qty = float(multibuy.group(1))
            total_price = float(multibuy.group(2))
            if qty > 0:
                return raw_price, total_price / qty

        # Standard Price Logic (finds biggest number, e.g. 2.99)
        matches = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", clean)
        if matches: 
            # If multiple numbers, usually the price is the one with decimals or the largest valid price
            # This handles "$10" (integers) which were missed before
            valid_nums = [float(m) for m in matches]
            return raw_price, valid_nums[0] 
            
        return raw_price, None
    except:
        return raw_price, None

def clean_dataframe(df):
    if df.empty: return df
    df = df[df['Price_Value'] > 0].copy()
    
    # Standardize casing
    df['Item'] = df['Item'].astype(str).str.title()
    
    # Ensure Original_Name exists (fill with Item if missing)
    if 'Original_Name' not in df.columns:
        df['Original_Name'] = df['Item']
        
    df['Valid_Until'] = df['Valid_Until'].astype(str).apply(lambda x: x.split('T')[0])
    
    def format_txt(row):
        txt = str(row['Price_Text'])
        val = row['Price_Value']
        # If text looks like just a number (e.g. "2.99"), add $
        if txt.replace('.','',1).isdigit(): return f"${val:.2f}"
        return txt
    
    df['Price_Text'] = df.apply(format_txt, axis=1)
    
    sort_cols = ['Store', 'Item']
    if 'Category' in df.columns: sort_cols = ['Category', 'Store', 'Item']
    df = df.sort_values(by=sort_cols)
    return df

# --- MAIN LOGIC ---
print(f">> Scanning flyers for Seton ({POSTAL_CODE})...")
flyers = get_active_flyers(POSTAL_CODE)

if not flyers:
    print("[!] No flyers found.")
    exit()

selected_flyers = []
for store in STORES:
    matches = [f for f in flyers if store.lower() in f.get('merchant', '').lower()]
    best = None
    for f in matches:
        name = f.get('name', '').lower()
        merch = f.get('merchant', '').lower()
        if "liquor" in name or "liquor" in merch: continue
        if "weekly" in name: best = f; break
        if not best: best = f
    if best:
        selected_flyers.append(best)
        print(f"   + Selected: {best['merchant']} (ID: {best['id']})")

new_deals = []
print("\n>> Extracting items...")

for flyer in selected_flyers:
    items = get_flyer_items(flyer['id'])
    print(f"   Processing {flyer['merchant']} ({len(items)} items)...")
    for item in items:
        name = item.get('name')
        price_txt, price_val = clean_price(item)
        valid_to = item.get('valid_to') or flyer.get('valid_to')
        if name:
            new_deals.append({
                'Date': datetime.date.today(),
                'Store': flyer['merchant'],
                'Original_Name': name,
                'Item': name, 
                'Price_Text': price_txt if price_txt else "Check Store",
                'Price_Value': price_val if price_val is not None else 0.0,
                'Valid_Until': valid_to
            })

# --- SMART AI CATEGORIZATION (WITH STRICT CACHING) ---
if new_deals:
    filename = 'seton_grocery_history.csv'
    known_cache = {}

    # 1. Load Cache from existing CSV
    # This prevents AI from running on anything we already know!
    if os.path.exists(filename):
        try:
            df_hist = pd.read_csv(filename)
            if 'Original_Name' not in df_hist.columns:
                df_hist['Original_Name'] = df_hist['Item']
                
            if 'Category' in df_hist.columns:
                # Create Dictionary: "Original Name" -> {Category: "Produce", Item: "Apple"}
                clean_cache = df_hist.drop_duplicates(subset=['Original_Name']).set_index('Original_Name')
                known_cache = clean_cache[['Item', 'Category']].to_dict('index')
                print(f"\n>> Loaded {len(known_cache)} known items from history (AI will skip these)")
        except Exception as e:
            print(f"[!] Cache Load Warning: {e}")

    # 2. Identify NEW items
    unique_names = list(set(d['Original_Name'] for d in new_deals))
    
    # CRITICAL: Only filter items that are NOT in the cache
    unknown_items = [name for name in unique_names if name not in known_cache]

    print(f"   Total unique items found today: {len(unique_names)}")
    print(f"   Actually NEW items for AI: {len(unknown_items)}")

    # 3. Send ONLY unknown items to Gemini
    ai_results = []
    if unknown_items:
        batch_size = 100
        for i in range(0, len(unknown_items), batch_size):
            batch = unknown_items[i : i + batch_size]
            print(f"   ...processing batch {i // batch_size + 1} ({len(batch)} items) with Gemini 2.5...")
            try:
                ai_results.extend(categorize_groceries(batch))
            except Exception as e:
                print(f"   [!] Batch failed: {e}")

    # 4. Merge AI results into Cache
    for item in ai_results:
        known_cache[item.original_name] = {
            'Category': item.category, 
            'Item': item.clean_name
        }

    # 5. Apply to all deals (using Cache for everything)
    for deal in new_deals:
        original = deal['Original_Name']
        if original in known_cache:
            data = known_cache[original]
            deal['Category'] = data['Category']
            deal['Item'] = data['Item']
            deal['Is_Deal'] = True
        else:
            deal['Category'] = "Uncategorized"
            deal['Is_Deal'] = False

    print(">> Categorization complete!")

    # --- SAVE TO LOCAL CSV ---
    df_new = pd.DataFrame(new_deals)
    df_new_clean = clean_dataframe(df_new)
    
    # Copy for Cloud (with timestamp)
    df_cloud = df_new_clean.copy()
    df_cloud['recorded_at'] = datetime.datetime.now()

    if os.path.exists(filename):
        try:
            df_hist = pd.read_csv(filename)
            # Align columns
            common_cols = df_hist.columns.intersection(df_new_clean.columns)
            df_combined = pd.concat([df_hist, df_new_clean[common_cols]])
        except:
            df_combined = df_new_clean
    else:
        df_combined = df_new_clean
            
    # Deduplicate
    df_combined.drop_duplicates(subset=['Store', 'Original_Name', 'Price_Text', 'Valid_Until'], inplace=True)
    df_combined.to_csv(filename, index=False)
    print(f"\n>> Local CSV updated. Total items: {len(df_combined)}")

    # --- UPLOAD TO SUPABASE (CLOUD) ---
    print(">> Uploading new deals to Cloud...")
    
    DB_PASSWORD = os.environ.get("SUPABASE_DB_PASS")
    
    if not DB_PASSWORD:
        print("[!] ERROR: Cloud upload skipped. 'SUPABASE_DB_PASS' not found in .env")
    else:
        DB_CONNECTION = f"postgresql://postgres.pjkbxjrsbjwqkzogdcwh:{DB_PASSWORD}@aws-1-ca-central-1.pooler.supabase.com:5432/postgres"
        
        try:
            engine = create_engine(DB_CONNECTION)
            
            # Prepare DataFrame for Supabase
            upload_df = df_cloud.rename(columns={'Item': 'product_name', 'Price_Value': 'price'})
            
            # Select columns
            if 'recorded_at' not in upload_df.columns:
                upload_df['recorded_at'] = datetime.datetime.now()
                
            upload_df = upload_df[['product_name', 'price', 'recorded_at']]
            
            # Upload
            upload_df.to_sql('scanned_prices', engine, if_exists='append', index=False)
            print(f">> Success! Sent {len(upload_df)} new deals to the App.")
            
        except Exception as e:
            print(f"[!] Cloud Upload Failed: {e}")

else:
    print("[!] No items found.")