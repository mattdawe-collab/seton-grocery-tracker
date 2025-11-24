import streamlit as st
import pandas as pd
import plotly.express as px
import os
import glob

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Seton Deals", page_icon="🥦", layout="centered")

stats_files = glob.glob("1810*.csv")
history_files = glob.glob("*history.csv")
STATS_FILE = stats_files[0] if stats_files else "1810024501-eng.csv"
HISTORY_FILE = history_files[0] if history_files else "seton_grocery_history.csv"

# --- 2. CSS ---
st.markdown("""
<style>
    .deal-card { 
        background-color: white; padding: 15px; border-radius: 10px; 
        box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 10px; 
        border-left: 5px solid #4CAF50; 
    }
    .deal-store { font-weight: bold; color: #555; font-size: 0.8em; text-transform: uppercase; }
    .deal-price { color: #d32f2f; font-weight: bold; font-size: 1.3em; }
    .deal-bench { color: #666; font-size: 0.9em; font-style: italic; }
    .savings-badge { 
        float: right; background: #e8f5e9; color: #2e7d32; 
        padding: 4px 10px; border-radius: 15px; font-weight: bold; font-size: 0.85em; 
    }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- 3. DATA LOADING ---
@st.cache_data
def load_data():
    if not os.path.exists(HISTORY_FILE): return pd.DataFrame()
    try:
        df = pd.read_csv(HISTORY_FILE)
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        return df
    except: return pd.DataFrame()

@st.cache_data
def load_benchmarks():
    if not os.path.exists(STATS_FILE): return {}
    try:
        header_row = 9
        with open(STATS_FILE, 'r', encoding='latin1', errors='replace') as f:
            for i, line in enumerate(f):
                if "Products" in line: header_row = i; break
        
        df = pd.read_csv(STATS_FILE, header=header_row, encoding='latin1')
        df.rename(columns={df.columns[0]: 'Product'}, inplace=True)
        df = df.dropna(subset=['Product'])
        
        numeric_df = df.select_dtypes(include=['number'])
        if not numeric_df.empty:
            df['Benchmark'] = df[numeric_df.columns[-3:]].mean(axis=1)
            return df.set_index('Product')['Benchmark'].to_dict()
        return {}
    except: return {}

def calculate_savings(df, benchmarks):
    # (StatsKey, Category)
    # Note: We handle the unit conversion dynamically below
    rules = {
        "ground beef": ("Ground beef, per kilogram 5", "Meat 🥩"),
        "pork loin": ("Pork loin cuts, per kilogram 5", "Meat 🥩"),
        "chicken breast": ("Chicken breasts, per kilogram 5", "Meat 🥩"),
        "bacon": ("Bacon, 500 grams 6", "Meat 🥩"),
        "butter": ("Butter, 454 grams 5", "Dairy 🧀"),
        "milk": ("Milk, 4 litres 5", "Dairy 🧀"),
        "eggs": ("Eggs, 1 dozen 5", "Dairy 🧀"),
        "potatoes": ("Potatoes, 4.54 kilograms 5", "Produce 🥦"),
        "carrots": ("Carrots, 1.36 kilograms 6", "Produce 🥦"),
        "apples": ("Apples, per kilogram 5", "Produce 🥦"),
        "avocados": ("Avocado, unit 5", "Produce 🥦"),
        "grapes": ("Grapes, per kilogram 5", "Produce 🥦"),
        "peanut butter": ("Peanut butter, 1 kilogram 6", "Pantry 🥫"),
        "coffee": ("Roasted or ground coffee, 340 grams 6", "Pantry 🥫"),
    }
    
    results = []
    for idx, row in df.iterrows():
        item = str(row['Item']).lower()
        price = row['Price_Value']
        price_txt = str(row['Price_Text']).lower()
        
        bench_val = None
        category = "Other"
        
        for k, (b_key, b_cat) in rules.items():
            if k in item:
                bench_val = benchmarks.get(b_key)
                category = b_cat
                break
        
        if bench_val and price > 0:
            # --- SMART UNIT CONVERSION ---
            # We convert the BENCHMARK to match the Flyer (for display)
            final_bench = bench_val
            unit_label = ""
            
            # Case 1: Meat/Fruit (Usually /lb vs StatsCan /kg)
            # If flyer says "/lb" OR price is < $10 for meat (heuristic)
            is_pound_price = "/lb" in price_txt or ("beef" in item and price < 12) or ("chicken" in item and price < 12) or ("pork" in item and price < 10) or ("apples" in item) or ("grapes" in item)
            
            if is_pound_price and "per kilogram" in b_key:
                final_bench = bench_val / 2.2046  # Convert kg benchmark to lb
                unit_label = "/lb"
            
            # Case 2: Carrots (StatsCan 1.36kg vs Flyer 3lb/5lb)
            elif "carrots" in item:
                if "3lb" in price_txt or price < 4:
                    # StatsCan is 1.36kg (3lb). Direct compare.
                    final_bench = bench_val 
                    unit_label = "(3lb)"
                elif "5lb" in price_txt:
                    # Convert 3lb benchmark to 5lb
                    final_bench = (bench_val / 3) * 5
                    unit_label = "(5lb)"

            # Case 3: Potatoes (StatsCan 4.54kg/10lb)
            elif "potatoes" in item:
                # StatsCan is already 10lb. Direct compare.
                unit_label = "(10lb)"

            # Calculate Savings
            savings_pct = (final_bench - price) / final_bench
            
            if savings_pct > 0.10:
                results.append({
                    "Date": row['Date'],
                    "Store": row['Store'],
                    "Category": category,
                    "Item": row['Item'],
                    "Price": f"${price:.2f}{unit_label}",
                    "Savings": savings_pct * 100,
                    "Benchmark": final_bench,
                    "Unit": unit_label
                })
                
    return pd.DataFrame(results)

# --- 4. UI EXECUTION ---
st.title("🛒 Seton Grocery Hub")

df_raw = load_data()
benchmarks = load_benchmarks()

if df_raw.empty or not benchmarks:
    st.error("Missing Data. Run `get_deals.py` and check Stats file.")
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
            
        df_deals = df_deals.sort_values("Savings", ascending=False)
        
        st.markdown("---")
        
        for _, row in df_deals.iterrows():
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
