import streamlit as st
import pandas as pd
import plotly.express as px
import os
import glob
from dotenv import load_dotenv
from google import genai

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Seton Deals Beta", page_icon="🥦", layout="centered")

# --- 2. AI SETUP (Safe for Cloud & Local) ---
load_dotenv() # Load the .env file
GEMINI_AVAILABLE = False
CLIENT = None

try:
    # Check .env first (Local), then secrets (Cloud)
    api_key = os.getenv("GEMINI_API_KEY") or (st.secrets["GEMINI_API_KEY"] if "GEMINI_API_KEY" in st.secrets else None)
    
    if api_key:
        CLIENT = genai.Client(api_key=api_key)
        GEMINI_AVAILABLE = True
except Exception as e:
    pass 

# --- 3. FILE DETECTION ---
stats_files = glob.glob("1810*.csv")
history_files = glob.glob("*history.csv")

STATS_FILE = stats_files[0] if stats_files else "1810024501-eng.csv"
HISTORY_FILE = history_files[0] if history_files else "seton_grocery_history.csv"

# --- 4. CSS STYLING (FIXED FOR DARK MODE) ---
st.markdown("""
<style>
    /* Force text color to black inside the card to prevent "White on White" in Dark Mode */
    .deal-card { 
        background-color: white; 
        color: #000000;  /* Forces dark text */
        padding: 15px; 
        border-radius: 10px; 
        box-shadow: 0 2px 5px rgba(0,0,0,0.1); 
        margin-bottom: 10px; 
        border-left: 5px solid #4CAF50; 
    }
    
    .score-card {
        background-color: #f8f9fa;
        color: #000000; /* Forces dark text */
        padding: 20px;
        border-radius: 15px;
        border: 2px solid #e9ecef;
        margin-bottom: 20px;
    }

    /* Explicitly black for the item title with !important to override system themes */
    .deal-item { 
        font-size: 1.1em; 
        font-weight: 600; 
        margin: 5px 0; 
        color: #000000 !important; 
    }

    .verdict-box {
        font-size: 1.5em; 
        font-weight: bold; 
        text-align: center; 
        padding: 10px; 
        border-radius: 8px; 
        color: white; /* Keep white text for the colored verdict box */
        margin-bottom: 15px;
    }
    
    .deal-store { font-weight: bold; color: #555; font-size: 0.8em; text-transform: uppercase; }
    .deal-price { color: #d32f2f; font-weight: bold; font-size: 1.2em; }
    
    .savings-badge { 
        float: right; 
        background: #e8f5e9; 
        color: #2e7d32; 
        padding: 2px 8px; 
        border-radius: 4px; 
        font-size: 0.8em; 
        font-weight: bold; 
    }
    
    .source-tag {
        font-size: 0.7em;
        color: #888;
        font-style: italic;
    }
    
    .stChatMessage {
        background-color: #f0f2f6;
        color: #000000; /* Ensure chat text is readable */
        border-radius: 10px;
        padding: 10px;
        border: 1px solid #ddd;
    }
    
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- 5. SESSION STATE ---
if 'view' not in st.session_state: st.session_state.view = 'list'
if 'selected_item' not in st.session_state: st.session_state.selected_item = None
if "messages" not in st.session_state: st.session_state.messages = []

# --- 6. DATA FUNCTIONS ---
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

# --- 7. HYBRID LOGIC HELPERS ---
def get_rules():
    return {
        "ground beef": ("Ground beef, per kilogram 5", "Meat 🥩"),
        "steak": ("Beef striploin cuts, per kilogram 5", "Meat 🥩"),
        "roast": ("Beef rib cuts, per kilogram 5", "Meat 🥩"), 
        "pork loin": ("Pork loin cuts, per kilogram 5", "Meat 🥩"),
        "bacon": ("Bacon, 500 grams 6", "Meat 🥩"),
        "chicken": ("Chicken breasts, per kilogram 5", "Meat 🥩"),
        "ham": ("Pork loin cuts, per kilogram 5", "Meat 🥩"),
        "butter": ("Butter, 454 grams 5", "Dairy 🧀"),
        "milk": ("Milk, 4 litres 5", "Dairy 🧀"),
        "cheese": ("Block cheese, 500 grams 6", "Dairy 🧀"),
        "yogurt": ("Yogurt, 500 grams 6", "Dairy 🧀"),
        "potatoes": ("Potatoes, 4.54 kilograms 5", "Produce 🥦"),
        "carrots": ("Carrots, 1.36 kilograms 6", "Produce 🥦"),
        "apples": ("Apples, per kilogram 5", "Produce 🥦"),
        "mandarin": ("Oranges, per kilogram 5", "Produce 🥦"),
        "oranges": ("Oranges, per kilogram 5", "Produce 🥦"),
        "squash": ("Carrots, 1.36 kilograms 6", "Produce 🥦"),
        "sweet potato": ("Sweet potatoes, per kilogram 5", "Produce 🥦"),
        "pasta": ("Dry or fresh pasta, 500 grams 6", "Pantry 🥫"),
        "flour": ("Wheat flour, 2.5 kilograms 6", "Pantry 🥫"),
        "coconut milk": ("Canned soup, 284 millilitres 6", "Pantry 🥫"),
        "salmon": ("Canned salmon, 213 grams 6", "Pantry 🥫"),
    }

def normalize_price(price, price_txt, item_name, rule_key):
    norm_price = price
    if "100 g" in price_txt or "100g" in price_txt: norm_price = price * 10
    is_pound = "/lb" in price_txt
    if not is_pound and price < 15 and "ea" not in price_txt:
        if "ribs" not in rule_key: is_pound = True
    if is_pound: norm_price = price * 2.2046
    if "mandarin" in rule_key: norm_price = price / 1.81
    elif "ribs" in rule_key and "swiss" in item_name: norm_price = price / 0.6
    return norm_price

def build_local_history(df_history):
    rules = get_rules()
    local_prices = {} 
    for _, row in df_history.iterrows():
        item = str(row['Item']).lower()
        price = row['Price_Value']
        price_txt = str(row['Price_Text']).lower()
        if "coffee" in item or "water" in item: continue
        for k in rules:
            if k in item:
                norm_p = normalize_price(price, price_txt, item, k)
                if k not in local_prices: local_prices[k] = []
                local_prices[k].append(norm_p)
                break
    local_benchmarks = {}
    for k, p_list in local_prices.items():
        if len(p_list) > 0: local_benchmarks[k] = sum(p_list) / len(p_list)
    return local_benchmarks

def calculate_savings(df_current, stats_benchmarks, local_benchmarks):
    rules = get_rules()
    results = []
    
    for idx, row in df_current.iterrows():
        item = str(row['Item']).lower()
        price = row['Price_Value']
        price_txt = str(row['Price_Text']).lower()
        
        if "water" in item or "foil" in item or "pan" in item: continue
        if "coffee" in item and "roast" in item: continue

        matched_rule = None
        matched_key = None
        for k in rules:
            if k in item:
                if k == "salmon" and "canned" not in item and "gold seal" not in item and price > 6: continue 
                matched_rule = rules[k]
                matched_key = k
                break
        
        if matched_rule and price > 0:
            stats_key, category = matched_rule
            final_bench = stats_benchmarks.get(stats_key, 0)
            source = "Nat'l Avg"
            
            # Hybrid Check
            if matched_key in local_benchmarks:
                local_avg = local_benchmarks[matched_key]
                if local_avg > 0:
                    final_bench = local_avg
                    source = "Seton Avg"

            if final_bench > 0:
                normalized_shelf_price = normalize_price(price, price_txt, item, matched_key)
                savings_pct = (final_bench - normalized_shelf_price) / final_bench
                
                display_bench = final_bench
                unit_label = ""
                is_pound = "/lb" in price_txt or (price < 15 and "ea" not in price_txt and category in ["Meat 🥩", "Produce 🥦"])
                if "ribs" in item and price > 8: is_pound = False 

                if is_pound:
                    display_bench = final_bench / 2.2046
                    unit_label = "/lb"
                elif "mandarin" in matched_key:
                    display_bench = final_bench * 1.81
                    unit_label = "(4lb Box)"
                elif "ribs" in matched_key and "swiss" in item:
                    display_bench = final_bench * 0.6
                    unit_label = "(600g)"
                elif "100 g" in price_txt or "100g" in price_txt:
                    display_bench = final_bench / 10
                    unit_label = "/100g"

                if savings_pct > 0.10 or "squash" in item:
                    results.append({
                        "Date": row['Date'], "Store": row['Store'], "Category": category,
                        "Item": row['Item'], "Price": f"${price:.2f}{unit_label}",
                        "Raw_Price": price, "Savings": savings_pct * 100, 
                        "Benchmark": display_bench, "Unit": unit_label,
                        "Source": source, "Search_Term": matched_rule[0].split(",")[0]
                    })
    return pd.DataFrame(results)

# --- 8. SMART SCORE CARD RENDERER (NEW: With Trend Logic) ---
def render_scorecard(item_row, df_full):
    st.markdown(f"### 🧐 Deal Analysis: {item_row['Item']}")
    
    # 1. THE VISUAL CARD
    sav = item_row['Savings']
    if sav > 40: verdict = "🔥 STOCK UP PRICE!"; color = "#2e7d32"
    elif sav > 20: verdict = "✅ GREAT DEAL"; color = "#4CAF50"
    else: verdict = "⚠️ AVERAGE PRICE"; color = "#f9a825"    
    st.markdown(f"""
    <div class="score-card">
        <div class="verdict-box" style="background-color: {color};">{verdict}</div>
        <div style="display:flex; justify-content:space-around; text-align:center;">
            <div>
                <div style="font-size:0.9em; color:#666;">Store Price</div>
                <div style="font-size:1.5em; font-weight:bold;">{item_row['Price']}</div>
            </div>
            <div>
                <div style="font-size:0.9em; color:#666;">{item_row['Source']}</div>
                <div style="font-size:1.5em; font-weight:bold;">${item_row['Benchmark']:.2f}</div>
            </div>
            <div>
                <div style="font-size:0.9em; color:#666;">Savings</div>
                <div style="font-size:1.5em; font-weight:bold; color:{color};">{int(sav)}%</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 2. GET & CLEAN HISTORY DATA
    search_term = item_row.get('Search_Term', item_row['Item'].split()[0])
    mask = df_full['Item'].str.contains(search_term, case=False, na=False)
    df_hist = df_full[mask].copy().sort_values("Date")

    # 3. SMART NORMALIZATION (Standardizes units for graph)
    rules = get_rules()
    rule_key = None
    
    # Find which rule applies to this item
    for k in rules:
        if k in item_row['Item'].lower():
            rule_key = k
            break
            
    smart_history = []
    if not df_hist.empty and rule_key:
        for _, h_row in df_hist.iterrows():
            # Normalize every historical price to the same standard (e.g. /lb or /kg)
            norm_p = normalize_price(
                h_row['Price_Value'], 
                str(h_row['Price_Text']).lower(), 
                str(h_row['Item']).lower(), 
                rule_key
            )
            
            # Formatting for the Tooltip
            tooltip_price = f"${norm_p:.2f}"
            
            # Scaling for display (match the benchmark unit logic)
            display_price = norm_p
            if "/lb" in item_row['Unit']: display_price = norm_p / 2.2046
            elif "4lb" in item_row['Unit']: display_price = norm_p * 1.81
            elif "600g" in item_row['Unit']: display_price = norm_p * 0.6
            elif "/100g" in item_row['Unit']: display_price = norm_p / 10
            
            smart_history.append({
                "Date": h_row['Date'],
                "Store": h_row['Store'],
                "Unit Price": display_price, 
                "Item": h_row['Item']
            })
        df_smart = pd.DataFrame(smart_history)
    else:
        # Fallback if no rule matches
        df_smart = df_hist.rename(columns={"Price_Value": "Unit Price"})

    # 4. CHART WITH CONTEXT
    if not df_smart.empty:
        st.markdown(f"#### 📉 Price Trend ({item_row['Unit'] or 'per unit'})")
        
        # Base Scatter Plot
        fig = px.scatter(df_smart, x="Date", y="Unit Price", color="Store", 
                      hover_data=["Item"], title=None)
        
        # Add Trendline
        fig.add_traces(px.line(df_smart, x="Date", y="Unit Price", color="Store").data)
        
        # Add BENCHMARK Line
        fig.add_hline(y=item_row['Benchmark'], line_dash="dash", line_color="red", 
                     annotation_text=f"Avg: ${item_row['Benchmark']:.2f}", 
                     annotation_position="bottom right")

        fig.update_layout(
            height=350, 
            margin=dict(l=20, r=20, t=20, b=20),
            yaxis_title=f"Price {item_row['Unit']}",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)

    # 5. AI DEEP DIVE
    st.markdown("### 🤖 AI Deep Dive")
    if GEMINI_AVAILABLE and CLIENT:
        with st.spinner("🧠 Analyzing price trends & value..."):
            hist_context = "No historical data."
            if not df_smart.empty:
                low = df_smart['Unit Price'].min()
                high = df_smart['Unit Price'].max()
                hist_context = f"History ({item_row['Unit']}): Low ${low:.2f}, High ${high:.2f}."

            prompt = f"""
            Analyze this grocery deal for a shopper in Calgary.
            Item: {item_row['Item']} at {item_row['Store']}
            Price: {item_row['Price']}
            Benchmark: ${item_row['Benchmark']:.2f}
            {hist_context}
            
            Provide:
            1. 📉 **Trend Analysis:** Is this a good time to buy based on the history?
            2. 🍳 **Quick Idea:** One simple way to cook or use this.
            3. 💡 **Verdict:** Buy Now or Wait?
            """
            
            try:
                response = CLIENT.models.generate_content(
                    model='gemini-2.0-flash', 
                    contents=prompt
                )
                st.info(response.text)
            except Exception as e:
                st.error(f"AI Error: {e}")
    else:
        st.warning("AI Key missing or invalid.")

    if st.button("⬅️ Back to Deals List"):
        st.session_state.selected_item = None
        st.session_state.view = 'list'
        st.rerun()

# --- 9. CHATBOT ENGINE (UPDATED FOR NEW SDK) ---
def run_chat_interface(df_deals):
    st.subheader("🤖 Ask the Grocery Bot")
    st.markdown("Ask questions like: *'Where is the cheapest butter?'* or *'What meat is on sale at Sobeys?'*")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask about deals..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            if not GEMINI_AVAILABLE or not CLIENT:
                st.error("⚠️ AI Key not found.")
            else:
                # Limit context to avoid token errors if list is huge
                cols_to_send = ['Store', 'Category', 'Item', 'Price', 'Price_Value']
                # Check if columns exist before filtering
                existing_cols = [c for c in cols_to_send if c in df_deals.columns]
                csv_context = df_deals[existing_cols].to_csv(index=False)
                
                system_prompt = f"""
                You are a friendly grocery assistant for Seton.
                Use ONLY this deal data to answer:
                {csv_context}
                
                If the answer isn't in the list, say "I don't see that deal this week."
                Keep answers short and helpful.
                """
                
                try:
                    response = CLIENT.models.generate_content(
                        model='gemini-2.0-flash', 
                        contents=f"{system_prompt}\n\nQuestion: {prompt}"
                    )
                    st.markdown(response.text)
                    st.session_state.messages.append({"role": "assistant", "content": response.text})
                except Exception as e:
                    st.error(f"AI Error: {e}")

# --- 10. MAIN APP LOGIC ---
st.title("🛒 Seton Grocery Hub")

df_raw = load_data()
stats_benchmarks = load_benchmarks()

if df_raw.empty:
    st.error("No data found. Please run `get_deals.py`.")
    st.stop()

local_benchmarks = build_local_history(df_raw)

# --- REPLACED TABS WITH SIDEBAR NAVIGATION ---
page = st.sidebar.radio("📍 Navigation", ["🔥 Top Deals", "📈 Price History", "🤖 Ask Bot"])
st.sidebar.markdown("---")

# Sidebar Filters
dates = sorted(df_raw['Date'].unique(), reverse=True)
selected_date = st.sidebar.selectbox("📅 Week Of:", dates)
all_stores = sorted(df_raw['Store'].unique())
selected_stores = st.sidebar.multiselect("🏪 Filter Stores:", all_stores, default=all_stores)

# Calc Deals
df_week = df_raw[df_raw['Date'] == selected_date]
df_deals = calculate_savings(df_week, stats_benchmarks, local_benchmarks)

if not df_deals.empty and selected_stores:
    df_deals = df_deals[df_deals['Store'].isin(selected_stores)]

# --- PAGE LOGIC ---
if page == "🔥 Top Deals":
    st.sidebar.markdown("---")
    sort_mode = st.sidebar.radio("Sort By:", ["Highest Savings %", "Flyer Order (Per Store)"])
    
    if st.session_state.view == 'list':
        if st.button("🔄 Refresh"): st.cache_data.clear(); st.rerun()
        if not df_deals.empty:
            # Handle Categories (if they exist)
            if 'Category' in df_deals.columns:
                cats = ["All"] + sorted(df_deals['Category'].dropna().unique().tolist())
                sel_cat = st.radio("Category", cats, horizontal=True)
                if sel_cat != "All": df_deals = df_deals[df_deals['Category'] == sel_cat]
            
            if sort_mode == "Highest Savings %":
                df_deals = df_deals.sort_values(by=['Store', 'Savings'], ascending=[True, False])
            else:
                df_deals = df_deals.sort_values(by=['Store'], kind='mergesort')

            st.markdown("### 🏆 Deals List")
            current_store = None
            for idx, row in df_deals.iterrows():
                if row['Store'] != current_store:
                    current_store = row['Store']
                    st.markdown(f"#### 🏪 {current_store}")
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"""
                    <div class="deal-card" style="margin-bottom:0px;">
                        <div class="savings-badge">SAVE {int(row['Savings'])}%</div>
                        <div class="deal-item">{row['Item']}</div>
                        <div class="deal-price">{row['Price']} <span style="font-size:0.6em; color:#888;">(Avg ${row['Benchmark']:.2f})</span></div>
                        <div class="source-tag">vs {row['Source']}</div>
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    if st.button("📊 Analyze", key=f"btn_{idx}"):
                        st.session_state.selected_item = row
                        st.session_state.view = 'detail'
                        st.rerun()
                st.markdown("---")
        else: st.info("No deals found.")
    elif st.session_state.view == 'detail':
        if st.session_state.selected_item is not None:
            render_scorecard(st.session_state.selected_item, df_raw)

elif page == "📈 Price History":
    st.subheader("🔎 Check a Price")
    query = st.text_input("Search (e.g. Beef)", "")
    if query:
        mask = df_raw['Item'].str.contains(query, case=False, na=False)
        df_hist = df_raw[mask].sort_values("Date")
        if not df_hist.empty:
            fig = px.line(df_hist, x="Date", y="Price_Value", color="Store", markers=True)
            st.plotly_chart(fig, use_container_width=True)
        else: st.warning("No history found.")

elif page == "🤖 Ask Bot":
    run_chat_interface(df_deals)