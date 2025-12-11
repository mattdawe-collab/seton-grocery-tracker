import requests
import pandas as pd
import datetime
import os
import time
import re
from classifier import categorize_groceries

# --- CONFIGURATION ---
POSTAL_CODE = "T3M1M9" # Seton / Cranston
STORES = [
    "Real Canadian Superstore",
    "Save-On-Foods",
    "Calgary Co-op",
    "Sobeys",
    "Safeway"
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
        if '/' in clean: 
            parts = clean.split('/')
            if len(parts) == 2:
                qty_match = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", parts[0])
                price_match = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", parts[1])
                if qty_match and price_match:
                    qty = float(qty_match[0])
                    total = float(price_match[0])
                    if qty > 0: return raw_price, total / qty
        
        matches = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", clean)
        if matches: return raw_price, float(matches[0])
        return raw_price, None
    except:
        return raw_price, None

def clean_dataframe(df):
    if df.empty: return df
    df = df[df['Price_Value'] > 0].copy()
    df['Item'] = df['Item'].astype(str).str.title()
    df['Valid_Until'] = df['Valid_Until'].astype(str).apply(lambda x: x.split('T')[0])
    
    def format_txt(row):
        txt = str(row['Price_Text'])
        val = row['Price_Value']
        if txt.replace('.','',1).isdigit(): return f"${val:.2f}"
        return txt
    
    df['Price_Text'] = df.apply(format_txt, axis=1)
    
    sort_cols = ['Store', 'Item']
    if 'Category' in df.columns: sort_cols = ['Category', 'Store', 'Item']
    df = df.sort_values(by=sort_cols)
    return df

# --- MAIN ---
print(f"🔎 Scanning flyers for Seton ({POSTAL_CODE})...")
flyers = get_active_flyers(POSTAL_CODE)

if not flyers:
    print("❌ No flyers found.")
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
        print(f"   ✅ Selected: {best['merchant']} (ID: {best['id']})")

new_deals = []
print("\n📥 Extracting items...")

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
                'Item': name,
                'Price_Text': price_txt if price_txt else "Check Store",
                'Price_Value': price_val if price_val is not None else 0.0,
                'Valid_Until': valid_to
            })

# --- SMART AI CATEGORIZATION ---
if new_deals:
    filename = 'seton_grocery_history.csv'
    known_cache = {}

    # 1. Load Cache from existing CSV (Learn from past runs!)
    if os.path.exists(filename):
        try:
            df_hist = pd.read_csv(filename)
            if 'Category' in df_hist.columns:
                # Build a dictionary of { "Item Name" : "Category" }
                known_cache = pd.Series(df_hist.Category.values, index=df_hist.Item).to_dict()
                print(f"\n🧠 Loaded {len(known_cache)} known items from history (Skipping AI for these!)")
        except:
            pass

    # 2. Identify which items are actually NEW
    unique_names = list(set(d['Item'] for d in new_deals))
    unknown_items = [name for name in unique_names if name not in known_cache]

    print(f"   Total unique items: {len(unique_names)}")
    print(f"   New items to classify: {len(unknown_items)} (Cached: {len(unique_names) - len(unknown_items)})")

    # 3. Send ONLY unknown items to Gemini
    ai_results = []
    if unknown_items:
        batch_size = 100  # <--- INCREASED FOR SPEED
        
        for i in range(0, len(unknown_items), batch_size):
            batch = unknown_items[i : i + batch_size]
            print(f"   ...processing batch {i // batch_size + 1} ({len(batch)} items)")
            try:
                ai_results.extend(categorize_groceries(batch))
            except Exception as e:
                print(f"   ⚠️ Batch failed: {e}")

    # 4. Merge AI results into the Cache
    for item in ai_results:
        # We use the ORIGINAL name as the key, but store the CLEAN name/Category
        known_cache[item.original_name] = {
            'Category': item.category, 
            'Clean_Name': item.clean_name,
            'Is_Deal': item.is_deal
        }

    # 5. Apply to all deals
    for deal in new_deals:
        original = deal['Item']
        
        # Check if we have data for this item (either from History or fresh AI)
        if original in known_cache:
            data = known_cache[original]
            
            # Handle if cache is just a simple string (old CSV) or rich object (new AI)
            if isinstance(data, dict):
                deal['Category'] = data['Category']
                deal['Item'] = data['Clean_Name'] # Swap dirty name for clean one
                deal['Is_Deal'] = data['Is_Deal']
            else:
                # Legacy cache (just string)
                deal['Category'] = data
                deal['Is_Deal'] = False
        else:
            deal['Category'] = "Uncategorized"
            deal['Is_Deal'] = False

    print("✨ Categorization complete!")

# --- SAVE ---
if new_deals:
    df = pd.DataFrame(new_deals)
    df_clean = clean_dataframe(df)
    
    if os.path.exists(filename):
        try:
            df_hist = pd.read_csv(filename)
            if 'Category' not in df_hist.columns: df_hist['Category'] = "Uncategorized"
            df_clean = pd.concat([df_hist, df_clean])
        except:
            pass
            
    df_clean.drop_duplicates(subset=['Store', 'Item', 'Price_Text', 'Valid_Until'], inplace=True)
    df_clean.to_csv(filename, index=False)
    
    print(f"\n✨ Success! Database now has {len(df_clean)} items.")
else:
    print("❌ No items found.")