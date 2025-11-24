import requests
import pandas as pd
import datetime
import os
import time
import re

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
            # Check all common keys where items hide
            return data.get('items') or data.get('spread_items') or []
    except:
        pass
    return []

def clean_price(item_dict):
    # FIXED: Added 'price' to the priority list
    keys = ['price', 'current_price', 'price_text', 'sale_price', 'original_price']
    
    raw_price = next((item_dict[k] for k in keys if item_dict.get(k)), None)
    
    if not raw_price: return None, None

    try:
        clean = str(raw_price).replace('$', '').replace('¢', '').lower().strip()
        
        # Handle "2/5.00"
        if '/' in clean: 
            parts = clean.split('/')
            if len(parts) == 2:
                # extract valid numbers from both sides
                qty_match = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", parts[0])
                price_match = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", parts[1])
                
                if qty_match and price_match:
                    qty = float(qty_match[0])
                    total = float(price_match[0])
                    if qty > 0:
                        return raw_price, total / qty
        
        # Handle "5.99" or "5.99 lb"
        matches = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", clean)
        if matches:
            return raw_price, float(matches[0])
            
        return raw_price, None
    except:
        return raw_price, None

def clean_dataframe(df):
    """Polishes the dataframe before saving."""
    if df.empty: return df
    
    # 1. Remove 0 prices
    df = df[df['Price_Value'] > 0].copy()
    
    # 2. Title Case Item Names
    df['Item'] = df['Item'].astype(str).str.title()
    
    # 3. Clean Dates (Remove Timezone)
    df['Valid_Until'] = df['Valid_Until'].astype(str).apply(lambda x: x.split('T')[0])
    
    # 4. Nice Price Formatting
    def format_txt(row):
        txt = str(row['Price_Text'])
        val = row['Price_Value']
        # If text is plain number like "14.99", add $
        if txt.replace('.','',1).isdigit():
            return f"${val:.2f}"
        return txt
    
    df['Price_Text'] = df.apply(format_txt, axis=1)
    
    # 5. Sort
    df = df.sort_values(by=['Store', 'Item'])
    
    return df

# --- MAIN ---
print(f"🔎 Scanning flyers for Seton ({POSTAL_CODE})...")
flyers = get_active_flyers(POSTAL_CODE)

if not flyers:
    print("❌ No flyers found.")
    exit()

selected_flyers = []
for store in STORES:
    # Find matches for this store
    matches = [f for f in flyers if store.lower() in f.get('merchant', '').lower()]
    
    best = None
    for f in matches:
        name = f.get('name', '').lower()
        merch = f.get('merchant', '').lower()
        
        # FIXED: Strict Liquor Exclusion
        if "liquor" in name or "liquor" in merch:
            continue
            
        if "weekly" in name: best = f; break
        if not best: best = f
        
    if best:
        selected_flyers.append(best)
        print(f"   ✅ Selected: {best['merchant']} (ID: {best['id']})")

new_deals = []
print("\n📥 Extracting & Cleaning items...")

for flyer in selected_flyers:
    items = get_flyer_items(flyer['id'])
    print(f"   Processing {flyer['merchant']} ({len(items)} items)...")
    
    for item in items:
        name = item.get('name')
        price_txt, price_val = clean_price(item)
        # Handle date formats
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

# --- SAVE ---
if new_deals:
    df = pd.DataFrame(new_deals)
    
    # Clean it!
    df_clean = clean_dataframe(df)
    
    filename = 'seton_grocery_history.csv'
    
    # Merge with history if exists
    if os.path.exists(filename):
        try:
            df_hist = pd.read_csv(filename)
            df_clean = pd.concat([df_hist, df_clean])
        except:
            pass
            
    # Dedup
    df_clean.drop_duplicates(subset=['Store', 'Item', 'Price_Text', 'Valid_Until'], inplace=True)
    
    df_clean.to_csv(filename, index=False)
    
    print(f"\n✨ Success! Database now has {len(df_clean)} items.")
    print("\nSample Data:")
    print(df_clean[['Store', 'Item', 'Price_Text']].head(5))
else:
    print("❌ No items found.")