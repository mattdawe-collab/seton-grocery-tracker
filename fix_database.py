import pandas as pd

# Load the file
filename = "seton_grocery_history.csv"
df = pd.read_csv(filename)

print(f"Original Row Count: {len(df)}")

# Sort by Date (descending) and Is_Deal (True first)
# This ensures the "best" version of the item floats to the top
df['Date'] = pd.to_datetime(df['Date'])
df = df.sort_values(by=['Date', 'Is_Deal'], ascending=[False, False])

# Drop duplicates based on the CLEAN 'Item' name, Store, Price, and Valid Date
# We keep the 'first' one (which due to sorting, is the Newest & Best one)
subset_cols = ['Store', 'Item', 'Price_Text', 'Valid_Until']
df_clean = df.drop_duplicates(subset=subset_cols, keep='first')

print(f"New Row Count: {len(df_clean)}")
print(f"Removed {len(df) - len(df_clean)} duplicates.")

# Save back to CSV
df_clean.to_csv(filename, index=False)
print("✅ Database fixed!")