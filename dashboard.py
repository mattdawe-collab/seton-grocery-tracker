import streamlit as st
import pandas as pd
import google.generativeai as genai
import plotly.express as px
import os
import re
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
PAGE_TITLE = "Calgary Grocery Hub"

# FILES
DATA_FILES = ["clean_grocery_data.csv", "seton_grocery_history.csv"]

# AI MODEL: Gemini 2.0 Flash is critical here for the large context window
AI_MODEL_NAME = "gemini-2.0-flash" 
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

st.set_page_config(page_title=PAGE_TITLE, layout="wide")

if not GEMINI_API_KEY:
    st.error("⚠️ API Key not found! Please check your .env file.")
    st.stop()

# --- DATA LOADING ---
@st.cache_data
def load_data():
    file_path = next((f for f in DATA_FILES if os.path.exists(f)), None)
    if not file_path: return pd.DataFrame()
    
    df = pd.read_csv(file_path)
    
    # Normalize Columns
    df = df.rename(columns={
        'Item': 'item', 'Store': 'store', 'Category': 'category', 
        'Price_Value': 'price', 'Date': 'date', 'Sub_Category': 'sub_category',
        'Original_Price': 'original_price', 'Valid_Until': 'valid_until',
        'display_category': 'display_category'
    })
    
    # Type Conversion
    df['price'] = pd.to_numeric(df['price'], errors='coerce')
    
    # Date Parsing (Critical for "Current Week" logic)
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        
    if 'valid_until' in df.columns:
        # We coerce errors so bad formats don't crash the app
        df['valid_until'] = pd.to_datetime(df['valid_until'], errors='coerce')

    # Ensure display_category exists
    if 'display_category' not in df.columns:
        df['display_category'] = df['category']
        
    return df

# --- ANALYSIS ENGINE ---
def get_item_stats(item_name, df):
    """Calculates historical stats for a specific item using the FULL history."""
    history = df[df['item'].str.lower() == item_name.lower()].copy()
    if history.empty: return None
    
    return {
        'avg': history['price'].mean(),
        'min': history['price'].min(),
        'max': history['price'].max(),
        'count': len(history),
        'last_seen': history.sort_values('date', ascending=False).head(5)[['date', 'store', 'price']]
    }

def run_ai_analysis(item_row, stats):
    """Asks AI for a specific opinion on the deal."""
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(AI_MODEL_NAME)
    
    stats_text = f"Avg: ${stats['avg']:.2f}, Low: ${stats['min']:.2f}" if stats else "No history."
    
    prompt = f"""
    Is this a good deal?
    Item: {item_row['item']} (${item_row['price']})
    Stats: {stats_text}
    Answer in 1 very short sentence.
    """
    try:
        return model.generate_content(prompt).text
    except:
        return "AI unavailable."

# --- MAIN APP ---
def main():
    st.title(f"🛒 {PAGE_TITLE}")
    
    # Load the MASTER DataFrame (contains everything: old and new)
    df = load_data()
    if df.empty:
        st.error("No data found.")
        return

    # TABS
    tab_finder, tab_analyst = st.tabs(["🔎 Deal Finder", "🤖 Ask Data"])

    # =========================================================
    # TAB 1: DEAL FINDER (Smart Filtering)
    # =========================================================
    with tab_finder:
        
        # 1. TIME CONTROL
        today = pd.Timestamp.now().floor('D')
        
        col_t1, col_t2 = st.columns([3, 1])
        with col_t1:
            st.caption(f"📅 Current Date: {today.strftime('%Y-%m-%d')}")
        with col_t2:
            show_expired = st.toggle("Show Expired Deals", value=False)

        # 2. CREATE THE "VIEW" DATAFRAME
        # If show_expired is False, we REMOVE old stuff.
        # This prevents the dropdowns from showing categories that aren't available this week.
        if not show_expired:
            # Logic: Keep if Valid Date is >= Today OR Valid Date is Missing (Ongoing)
            list_view_df = df[ (df['valid_until'] >= today) | (df['valid_until'].isna()) ].copy()
        else:
            list_view_df = df.copy()

        if list_view_df.empty:
            st.warning("No active deals found! Try turning on 'Show Expired Deals' to see history.")

        # 3. DYNAMIC FILTERS (Generated from the View DF, not the Master DF)
        cats = ["All"] + sorted(list_view_df['display_category'].dropna().unique().tolist())
        selected_cat = st.radio("Category", cats, horizontal=True, label_visibility="collapsed")
        
        c1, c2 = st.columns(2)
        with c1:
            # Sub-Category Filter
            if selected_cat == "All":
                cat_df = list_view_df
            else:
                cat_df = list_view_df[list_view_df['display_category'] == selected_cat]
            
            sub_cats = sorted(cat_df['sub_category'].dropna().unique().tolist())
            selected_sub = st.multiselect("Sub-Category", sub_cats)
            
        with c2:
            # Store Filter
            all_stores = sorted(list_view_df['store'].unique())
            store_filter = st.multiselect("Stores", all_stores, default=all_stores)

        # 4. APPLY FILTERS
        filtered_df = cat_df.copy()
        if selected_sub:
            filtered_df = filtered_df[filtered_df['sub_category'].isin(selected_sub)]
        if store_filter:
            filtered_df = filtered_df[filtered_df['store'].isin(store_filter)]

        st.markdown("---")

        # 5. PERFORMANCE LIMITER
        DISPLAY_LIMIT = 50 
        total_items = len(filtered_df)
        
        if total_items > DISPLAY_LIMIT:
            st.info(f"Showing top {DISPLAY_LIMIT} of {total_items} items. Use filters to narrow down.")
            display_df = filtered_df.head(DISPLAY_LIMIT)
        else:
            display_df = filtered_df

        # 6. DISPLAY ITEMS
        for store in display_df['store'].unique():
            store_items = display_df[display_df['store'] == store]
            if store_items.empty: continue
            
            with st.expander(f"🏪 {store} ({len(store_items)})", expanded=True):
                for _, row in store_items.iterrows():
                    c1, c2, c3 = st.columns([3, 1, 1])
                    
                    # Date Indicator
                    valid_date = row.get('valid_until')
                    if pd.isna(valid_date):
                        date_str = "Ongoing"
                        status_icon = "⚪"
                    elif valid_date < today:
                        date_str = f"Expired: {valid_date.strftime('%b %d')}"
                        status_icon = "🔴"
                    else:
                        date_str = f"Ends: {valid_date.strftime('%b %d')}"
                        status_icon = "🟢"

                    with c1:
                        st.write(f"**{row['item']}**")
                        st.caption(f"{status_icon} {date_str} | {row.get('sub_category','')}")
                    
                    with c2:
                        price_display = f"**${row['price']:.2f}**"
                        if row.get('savings_pct', 0) > 0:
                            price_display += f" (🔥 {int(row['savings_pct'])}%)"
                        st.markdown(price_display)

                    with c3:
                        # KEY FEATURE: We pass the MASTER 'df' here so analysis sees history
                        if st.button("Analyze 🔍", key=f"btn_{row.name}"):
                            stats = get_item_stats(row['item'], df) # <--- Uses FULL history
                            st.markdown("#### 📊 Analysis")
                            
                            if stats:
                                delta = stats['avg'] - row['price']
                                color = "normal" if delta < 0 else "inverse"
                                st.metric("Value vs Avg", f"${row['price']:.2f}", f"{delta:+.2f}", delta_color=color)
                                st.dataframe(stats['last_seen'], hide_index=True)
                            
                            with st.spinner("Checking..."):
                                opinion = run_ai_analysis(row, stats)
                                st.success(f"🤖 {opinion}")
                            st.divider()

    # =========================================================
    # TAB 2: ASK DATA (Context Aware)
    # =========================================================
    with tab_analyst:
        st.header("🤖 Data Analyst")
        st.caption(f"Context: {len(df)} records (Current + History).")
        
        if "messages" not in st.session_state:
            st.session_state.messages = []
            
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                
        if prompt := st.chat_input("Ex: 'Where is the cheapest butter this week?'"):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.write(prompt)
            
            with st.chat_message("assistant"):
                with st.spinner("Analyzing full dataset..."):
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel(AI_MODEL_NAME)
                    
                    full_context = df.to_csv(index=False)
                    today_str = pd.Timestamp.now().strftime('%Y-%m-%d')
                    
                    ai_prompt = f"""
                    You are a Python Data Analyst.
                    
                    CONTEXT:
                    - TODAY IS: {today_str}
                    - 'valid_until' column shows expiration.
                    - If 'valid_until' < {today_str}, the deal is EXPIRED.
                    
                    FULL DATASET (CSV):
                    {full_context}
                    
                    USER QUESTION: {prompt}
                    
                    INSTRUCTIONS:
                    1. If user asks for "active" or "current" deals, filter out expired rows.
                    2. If user asks for "trends" or "history", use all rows.
                    3. If graphing, return python code wrapped in ```python ... ``` using plotly.express as px.
                    """
                    
                    try:
                        response = model.generate_content(ai_prompt).text
                        
                        code_match = re.search(r"```python(.*?)```", response, re.DOTALL)
                        if code_match:
                            code = code_match.group(1)
                            local_vars = {"df": df, "px": px, "pd": pd}
                            exec(code, {}, local_vars)
                            if 'fig' in local_vars:
                                st.plotly_chart(local_vars['fig'])
                                st.session_state.messages.append({"role": "assistant", "content": "📊 *Graph Generated*"})
                            else:
                                st.error("AI generated code but failed to create graph.")
                        else:
                            st.write(response)
                            st.session_state.messages.append({"role": "assistant", "content": response})
                            
                    except Exception as e:
                        st.error(f"AI Error: {e}")

if __name__ == "__main__":
    main()