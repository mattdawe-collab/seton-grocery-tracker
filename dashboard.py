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

# --- 4. DATA FUNCTIONS ---
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
    # EXPANDED VOCABULARY
    rules = {
        # --- MEAT (Consolidated) ---
        "ground beef": ("Ground beef, per kilogram 5", 2.20, "Meat 🥩"),
        "hamburger": ("Ground beef, per kilogram 5", 2.20, "Meat 🥩"),
        "stewing beef": ("Beef stewing cuts, per kilogram 5", 2.20, "Meat 🥩"),
        "steak": ("Beef striploin cuts, per kilogram 5", 2.20, "Meat 🥩"),
        "sirloin": ("Beef top sirloin cuts, per kilogram 5", 2.20, "Meat 🥩"),
        "roast": ("Beef rib cuts, per kilogram 5", 2.20, "Meat 🥩"),
        "pork loin": ("Pork loin cuts, per kilogram 5", 2.20, "Meat 🥩"),
        "chops": ("Pork loin cuts, per kilogram 5", 2.20, "Meat 🥩"),
        "ribs": ("Pork rib cuts, per kilogram 5", 2.20, "Meat 🥩"),
        "pork shoulder": ("Pork shoulder cuts, per kilogram 5", 2.20, "Meat 🥩"),
        "bacon": ("Bacon, 500 grams 6", 1.0, "Meat 🥩"),
        "wieners": ("Wieners, 400 grams 6", 1.0, "Meat 🥩"),
        "hot dog": ("Wieners, 400 grams 6", 1.0, "Meat 🥩"),
        "pork": ("Pork loin cuts, per kilogram 5", 2.20, "Meat 🥩"),
        "chicken breast": ("Chicken breasts, per kilogram 5", 2.20, "Meat 🥩"),
        "chicken thigh": ("Chicken thigh, per kilogram 5", 2.20, "Meat 🥩"),
        "drumstick": ("Chicken drumsticks, per kilogram 5", 2.20, "Meat 🥩"),
        "whole chicken": ("Whole chicken, per kilogram 5", 2.20, "Meat 🥩"),
        "turkey": ("Whole chicken, per kilogram 5", 2.20, "Meat 🥩"), 
        
        # --- SEAFOOD ---
        "salmon": ("Salmon, per kilogram 5", 2.20, "Seafood 🐟"),
        
        # --- DAIRY (Expanded) ---
        "butter": ("Butter, 454 grams 5", 1.0, "Dairy 🧀"),
        "milk": ("Milk, 4 litres 5", 1.0, "Dairy 🧀"),
        "eggs": ("Eggs, 1 dozen 5", 1.0, "Dairy 🧀"),
        "cheese": ("Block cheese, 500 grams 6", 1.0, "Dairy 🧀"),
        "cheddar": ("Block cheese, 500 grams 6", 1.0, "Dairy 🧀"),
        "mozarella": ("Block cheese, 500 grams 6", 1.0, "Dairy 🧀"),
        "yogurt": ("Yogurt, 500 grams 6", 1.0, "Dairy 🧀"),
        "cream": ("Cream, 1 litre 5", 1.0, "Dairy 🧀"),
        "margarine": ("Margarine, 907 grams 6", 1.0, "Dairy 🧀"),
        
        # --- PRODUCE (Expanded) ---
        "potatoes": ("Potatoes, 4.54 kilograms 5", 1.0, "Produce 🥦"),
        "carrots": ("Carrots, 1.36 kilograms 6", 0.45, "Produce 🥦"),
        "apples": ("Apples, per kilogram 5", 2.20, "Produce 🥦"),
        "avocados": ("Avocado, unit 5", 1.0, "Produce 🥦"),
        "grapes": ("Grapes, per kilogram 5", 2.20, "Produce 🥦"),
        "bananas": ("Bananas, per kilogram 5", 2.20, "Produce 🥦"),
        "pears": ("Pears, per kilogram 5", 2.20, "Produce 🥦"),
        "tomatoes": ("Tomatoes, per kilogram 5", 2.20, "Produce 🥦"),
        "onions": ("Onions, per kilogram 5", 2.20, "Produce 🥦"),
        "oranges": ("Oranges, per kilogram 5", 2.20, "Produce 🥦"),
        "lettuce": ("Romaine lettuce, unit 5", 1.0, "Produce 🥦"),
        "romaine": ("Romaine lettuce, unit 5", 1.0, "Produce 🥦"),
        "peppers": ("Peppers, per kilogram 5", 2.20, "Produce 🥦"),
        "cucumber": ("Cucumber, unit 5", 1.0, "Produce 🥦"),
        "mushrooms": ("Mushrooms, 227 grams 6", 1.0, "Produce 🥦"),
        "strawberries": ("Strawberries, 454 grams 6", 1.0, "Produce 🥦"),
        "celery": ("Celery, unit 5", 1.0, "Produce 🥦"),
        "sweet potato": ("Sweet potatoes, per kilogram 5", 2.20, "Produce 🥦"),
        "yams": ("Sweet potatoes, per kilogram 5", 2.20, "Produce 🥦"),
        
        # --- PANTRY ---
        "peanut butter": ("Peanut butter, 1 kilogram 6", 1.0, "Pantry 🥫"),
        "coffee": ("Roasted or ground coffee, 340 grams 6", 1.0, "Pantry 🥫"),
        "pasta": ("Dry or fresh pasta, 500 grams 6", 1.0, "Pantry 🥫"),
        "flour": ("Wheat flour, 2.5 kilograms 6", 1.0, "Pantry 🥫"),
        "sugar": ("White sugar, 2 kilograms 6", 1.0, "Pantry 🥫"),
    }
    
    results = []
    for idx, row in df.iterrows():
        item = str(row['Item']).lower()
        price = row['Price_Value']
        price_txt = str(row['Price_Text']).lower()
        bench_val = None
        category = "Other"
        
        for k, (b_key, b_factor, b_cat) in rules.items():
            if k in item:
                bench_val = benchmarks.get(b_key)
                category = b_cat
                break
        
        if bench_val and price > 0:
            final_bench = bench_val
            unit_label = ""
            
            # --- SMART UNIT LOGIC ---
            # 1. Weight-based items (Meat/Produce)
            is_pound = "/lb" in price_txt or (category in ["Meat 🥩", "Produce 🥦"] and price < 15 and "ea" not in price_txt)
            
            if is_pound and "per kilogram" in str(b_key):
                final_bench = bench_val / 2.2046
                unit_label = "/lb"
            
            # 2. Specific Bag/Pack Fixes
            elif "carrots" in item:
                if "3lb" in price_txt: unit_label = "(3lb)"
                elif "5lb" in price_txt: final_bench = (bench_val/1.36)*2.27; unit_label = "(5lb)"
            elif "onions" in item:
                if "3lb" in price_txt: final_bench = (bench_val)*1.36; unit_label = "(3lb)"
            elif "potatoes" in item:
                if "10lb" in price_txt: unit_label = "(10lb)"
                elif "5lb" in price_txt: final_bench = bench_val/2; unit_label = "(5lb)"
            elif "strawberries" in item:
                unit_label = "(454g)" # Clamshell matches StatsCan
            elif "mushrooms" in item:
                unit_label = "(227g)" # Pack matches StatsCan

            savings_pct = (final_bench - price) / final_bench
            
            if savings_pct > 0.01:
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

# --- 5. UI EXECUTION ---
st.title("🛒 Seton Grocery Hub")

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
        
        df_deals = df_deals.sort_values("Savings", ascending=False)
        
        # Limit to Top 20
        df_display = df_deals.head(20)
        
        st.markdown(f"**Showing Top {len(df_display)} Deals**")
        st.markdown("---")
        
        for _, row in df_display.iterrows():
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