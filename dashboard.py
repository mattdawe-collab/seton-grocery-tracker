import streamlit as st
import pandas as pd
import plotly.express as px
import os
import glob

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Seton Deals", page_icon="🥦", layout="centered")

# --- 2. FILE DETECTION ---
stats_files = glob.glob("1810*.csv")
history_files = glob.glob("*history.csv")

STATS_FILE = stats_files[0] if stats_files else "1810024501-eng.csv"
HISTORY_FILE = history_files[0] if history_files else "seton_grocery_history.csv"

# --- 3. CSS STYLING ---
st.markdown("""
<style>
    .deal-card { 
        background-color: white; 
        padding: 15px; 
        border-radius: 10px; 
        box-shadow: 0 2px 5px rgba(0,0,0,0.1); 
        margin-bottom: 10px; 
        border-left: 5px solid #4CAF50; 
    }
    .deal-store { font-weight: bold; color: #555; font-size: 0.8em; text-transform: uppercase; }
    .deal-price { color: #d32f2f; font-weight: bold; font-size: 1.2em; }
    .deal-item { font-size: 1.1em; font-weight: 600; margin: 5px 0; }
    .savings-badge { 
        float: right; 
        background: #e8f5e9; 
        color: #2e7d32; 
        padding: 2px 8px; 
        border-radius: 4px; 
        font-size: 0.8em; 
        font-weight: bold; 
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- 4. DATA FUNCTIONS (Auto-Refresh) ---
@st.cache_data(ttl="1h")
def load_data():
    if not os.path.exists(HISTORY_FILE): return pd.DataFrame()
    try:
        df = pd.read_csv(HISTORY_FILE)
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl="1h")
def load_benchmarks():
    if not os.path.exists(STATS_FILE): return {}
    try:
        header_row = 0
        with open(STATS_FILE, 'r', encoding='latin1', errors='replace') as f:
            for i, line in enumerate(f):
                if "Products" in line: header_row = i; break
        
        df = pd.read_csv(STATS_FILE, header=header_row, encoding='latin1')
        df.rename(columns={df.columns[0]: 'Product'}, inplace=True)
        df = df.dropna(subset=['Product'])
        
        numeric = df.select_dtypes(include=['number'])
        if not numeric.empty:
            df['Benchmark'] = df[numeric.columns[-3:]].mean(axis=1)
            return df.set_index('Product')['Benchmark'].to_dict()
        return {}
    except: return {}

def calculate_savings(df, benchmarks):
    # RULES: "keyword": ("StatsCan Key", "Category")
    rules = {
        # --- MEAT 🥩 ---
        "ground beef": ("Ground beef, per kilogram 5", "Meat 🥩"),
        "hamburger": ("Ground beef, per kilogram 5", "Meat 🥩"),
        "stewing beef": ("Beef stewing cuts, per kilogram 5", "Meat 🥩"),
        "steak": ("Beef striploin cuts, per kilogram 5", "Meat 🥩"),
        "roast": ("Beef rib cuts, per kilogram 5", "Meat 🥩"), 
        "pork loin": ("Pork loin cuts, per kilogram 5", "Meat 🥩"),
        "chops": ("Pork loin cuts, per kilogram 5", "Meat 🥩"),
        "ribs": ("Pork rib cuts, per kilogram 5", "Meat 🥩"),
        "pork shoulder": ("Pork shoulder cuts, per kilogram 5", "Meat 🥩"),
        "bacon": ("Bacon, 500 grams 6", "Meat 🥩"),
        "ham": ("Pork loin cuts, per kilogram 5", "Meat 🥩"), # Ham Proxy
        "chicken": ("Chicken breasts, per kilogram 5", "Meat 🥩"),
        "turkey": ("Whole chicken, per kilogram 5", "Meat 🥩"),
        
        # --- DAIRY 🧀 ---
        "butter": ("Butter, 454 grams 5", "Dairy 🧀"),
        "milk": ("Milk, 4 litres 5", "Dairy 🧀"),
        "cheese": ("Block cheese, 500 grams 6", "Dairy 🧀"),
        "yogurt": ("Yogurt, 500 grams 6", "Dairy 🧀"),
        "margarine": ("Margarine, 907 grams 6", "Dairy 🧀"),
        
        # --- PRODUCE 🥦 ---
        "potatoes": ("Potatoes, 4.54 kilograms 5", "Produce 🥦"),
        "carrots": ("Carrots, 1.36 kilograms 6", "Produce 🥦"),
        "apples": ("Apples, per kilogram 5", "Produce 🥦"),
        "mandarin": ("Oranges, per kilogram 5", "Produce 🥦"),
        "oranges": ("Oranges, per kilogram 5", "Produce 🥦"),
        "lettuce": ("Romaine lettuce, unit 5", "Produce 🥦"),
        "squash": ("Carrots, 1.36 kilograms 6", "Produce 🥦"), # Proxy for 'Cheap Veg'
        "sweet potato": ("Sweet potatoes, per kilogram 5", "Produce 🥦"),
        
        # --- PANTRY 🥫 ---
        "pasta": ("Dry or fresh pasta, 500 grams 6", "Pantry 🥫"),
        "flour": ("Wheat flour, 2.5 kilograms 6", "Pantry 🥫"),
        "broth": ("Canned soup, 284 millilitres 6", "Pantry 🥫"), 
        "coconut milk": ("Canned soup, 284 millilitres 6", "Pantry 🥫"), 
        "salmon": ("Canned salmon, 213 grams 6", "Pantry 🥫"), 
    }
    
    results = []
    for idx, row in df.iterrows():
        item = str(row['Item']).lower()
        price = row['Price_Value']
        price_txt = str(row['Price_Text']).lower()
        
        # --- 1. EXCLUSION FILTER (The "No False Positives" Wall) ---
        if "water" in item or "foil" in item or "pan" in item: 
            continue # Removes "Coconut Water" and "Roasting Pans" from Roast
        if "coffee" in item and "roast" in item:
            continue # Removes "Roasted Coffee" from Meat

        matched_rule = None
        for k in rules:
            if k in item:
                # Special check for Canned vs Fresh Salmon
                if k == "salmon" and "canned" not in item and "gold seal" not in item and price > 6:
                     # Skip fresh salmon if we don't have a fresh benchmark, or let it fail savings check
                     continue 
                matched_rule = rules[k]
                break
        
        if matched_rule and price > 0:
            b_key, category = matched_rule
            bench_val = benchmarks.get(b_key, 0)
            
            if bench_val > 0:
                final_bench = bench_val
                unit_label = ""
                price_comparison = price

                # --- 2. THE "100g" TRAP DETECTOR ---
                if "100 g" in price_txt or "100g" in price_txt:
                    # If price is per 100g, multiply by 10 to get per kg for comparison
                    price_comparison = price * 10
                    # Note: We keep 'price' as is for display, but use 'price_comparison' for math
                
                # --- 3. STANDARD UNIT DETECTION ---
                # Check if price is likely Per Pound
                is_pound = "/lb" in price_txt or (price < 15 and "ea" not in price_txt and category in ["Meat 🥩", "Produce 🥦"])
                if "ribs" in item and price > 8: is_pound = False # Boxed Ribs exception

                if is_pound and "per kilogram" in b_key:
                    final_bench = bench_val / 2.2046
                    unit_label = "/lb"
                
                # --- 4. SPECIFIC ITEM OVERRIDES ---
                if "mandarin" in item: 
                    # Compare Box Price to (Benchmark/kg * 1.8kg)
                    # 4lb = ~1.81kg
                    final_bench = (bench_val * 1.81)
                    unit_label = "(4lb Box)"
                elif "ribs" in item and "swiss chalet" in item:
                    # 600g Box
                    final_bench = (bench_val * 0.6)
                    unit_label = "(600g)"
                elif "bacon" in item:
                    unit_label = "(500g)"
                elif "squash" in item:
                    # Squash is cheap, benchmark against carrots isn't perfect but works for sorting
                    unit_label = "/lb"

                # --- 5. CALCULATE SAVINGS ---
                savings_pct = (final_bench - price_comparison) / final_bench
                
                # Only show if savings > 10% OR it's a known "Good Deal" item like Squash
                if savings_pct > 0.10 or "squash" in item:
                    results.append({
                        "Date": row['Date'], "Store": row['Store'], "Category": category,
                        "Item": row['Item'], "Price": f"${price:.2f}{unit_label}",
                        "Savings": savings_pct * 100, "Benchmark": final_bench, "Unit": unit_label
                    })
                
    return pd.DataFrame(results)

def render_card(row):
    st.markdown(f"""
    <div class="deal-card">
        <div class="savings-badge">SAVE {int(row['Savings'])}%</div>
        <div class="deal-store">{row['Store']} &nbsp;•&nbsp; {row['Category']}</div>
        <div class="deal-item">{row['Item']}</div>
        <div style="display:flex; align-items:baseline; gap:10px;">
            <span class="deal-price">{row['Price']}</span>
            <span class="deal-bench">Avg: ${row['Benchmark']:.2f}{row['Unit']}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- 6. UI EXECUTION ---
st.title("🛒 Seton Grocery Hub")

if st.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

df_raw = load_data()
benchmarks = load_benchmarks()

if df_raw.empty or not benchmarks:
    st.error("Missing Data. Run `get_deals.py`.")
    st.stop()

tab1, tab2 = st.tabs(["🔥 Top Deals", "📈 Price History"])

with tab1:
    dates = sorted(df_raw['Date'].unique(), reverse=True)
    selected_date = st.selectbox("📅 Week Of:", dates)
    
    df_week = df_raw[df_raw['Date'] == selected_date]
    df_deals = calculate_savings(df_week, benchmarks)
    
    if not df_deals.empty:
        cats = ["All"] + sorted(df_deals['Category'].unique().tolist())
        sel_cat = st.radio("Category", cats, horizontal=True)
        
        if sel_cat != "All":
            df_deals = df_deals[df_deals['Category'] == sel_cat]
        
        # --- IMPROVED SORTING ---
        # 1. Store (A-Z)
        # 2. Category (A-Z)
        # 3. Savings (High to Low)
        df_deals = df_deals.sort_values(by=['Store', 'Category', 'Savings'], ascending=[True, True, False])
        
        # Display Logic
        if sel_cat == "All":
            st.markdown("### 🏆 Top 5 Deals Per Store")
            for store in df_deals['Store'].unique():
                st.markdown(f"**{store}**")
                # Show Top 5 items for this store
                store_deals = df_deals[df_deals['Store'] == store].head(5)
                for _, row in store_deals.iterrows():
                    render_card(row)
        else:
            # Show all deals if specific category selected
            for _, row in df_deals.iterrows():
                render_card(row)
    else:
        st.info("No major deals found this week.")

with tab2:
    st.subheader("🔎 Check a Price")
    query = st.text_input("Search (e.g. Beef)", "")
    if query:
        mask = df_raw['Item'].str.contains(query, case=False, na=False)
        df_hist = df_raw[mask].sort_values("Date")
        if not df_hist.empty:
            fig = px.line(df_hist, x="Date", y="Price_Value", color="Store", markers=True, title=f"History: {query}")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_hist[['Date', 'Store', 'Item', 'Price_Text']], hide_index=True)
        else:
            st.warning("No history found.")