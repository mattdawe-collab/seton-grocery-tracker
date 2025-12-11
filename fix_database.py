import pandas as pd
import time
import os
from classifier import categorize_groceries

# --- CONFIGURATION ---
FILENAME = 'seton_grocery_history.csv'
BATCH_SIZE = 50

# 1. Load the Database
if not os.path.exists(FILENAME):
    print("❌ No database found.")
    exit()

df = pd.read_csv(FILENAME)
original_count = len(df)
print(f"📂 Loaded {original_count} rows.")

# 2. Identify Broken Items
# We look for "Uncategorized", NULLs, or weird encoding artifacts
mask = (df['Category'] == 'Uncategorized') | (df['Category'].isna())
uncategorized_items = df[mask]['Item'].unique().tolist()

print(f"📉 Found {len(uncategorized_items)} unique items to categorize/clean.")

# 3. Process with AI (If needed)
if uncategorized_items:
    print("🚀 Starting AI processing...")
    fixed_data = {}

    for i in range(0, len(uncategorized_items), BATCH_SIZE):
        batch = uncategorized_items[i : i + BATCH_SIZE]
        print(f"   Processing batch {i // BATCH_SIZE + 1} / {(len(uncategorized_items) // BATCH_SIZE) + 1}...")
        
        try:
            results = categorize_groceries(batch)
            for item in results:
                fixed_data[item.original_name] = {
                    'Category': item.category,
                    'Clean_Name': item.clean_name,
                    'Is_Deal': item.is_deal
                }
            # Sleep to protect Free Tier limits
            time.sleep(4) 
        except Exception as e:
            print(f"   ⚠️ Error on batch: {e}")
            time.sleep(10)

    # 4. Apply Updates to DataFrame
    print("\n💾 Applying AI fixes...")
    for index, row in df.iterrows():
        original_name = row['Item']
        if original_name in fixed_data and (row['Category'] == 'Uncategorized' or pd.isna(row['Category'])):
            data = fixed_data[original_name]
            df.at[index, 'Category'] = data['Category']
            df.at[index, 'Item'] = data['Clean_Name'] # <--- This fixes the weird chars
            df.at[index, 'Is_Deal'] = data['Is_Deal']

else:
    print("✅ No uncategorized items found. Moving to duplicate check...")

# --- 5. THE DUPLICATE CHECK (NEW) ---
print("\n🧹 Running Duplicate Remover...")

# We check for duplicates based on: Store, Clean Name, Price, and Valid Date.
# We ignore 'Date' (scraped date) because seeing the same deal twice isn't useful.
dedupe_cols = ['Store', 'Item', 'Price_Text', 'Valid_Until']

before_dedupe = len(df)
df.drop_duplicates(subset=dedupe_cols, keep='first', inplace=True)
removed_count = before_dedupe - len(df)

if removed_count > 0:
    print(f"   ✂️ Removed {removed_count} duplicate rows!")
    print("      (These were likely items that became identical after the name cleanup)")
else:
    print("   ✅ No duplicates found.")

# 6. Save
df.to_csv(FILENAME, index=False)
print(f"✨ Done! Database optimized from {original_count} to {len(df)} rows.")