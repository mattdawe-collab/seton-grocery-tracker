import streamlit as st
import pandas as pd
import google.generativeai as genai
import plotly.express as px
import os
import re
from datetime import timedelta
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
PAGE_TITLE = "Calgary Grocery Hub"

# FILES
DATA_FILES = ["clean_grocery_data.csv", "seton_grocery_history.csv"]

# AI MODEL
AI_MODEL_NAME = "gemini-2.0-flash" 
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

st.set_page_config(page_title=PAGE_TITLE, layout="wide", page_icon="🛒")

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
    df = df[df['price'] > 0.01] 

    # Date Parsing
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
    if 'valid_until' in df.columns:
        df['valid_until'] = pd.to_datetime(df['valid_until'], errors='coerce')

    # Calculate Savings
    if 'original_price' in df.columns:
        df['original_price'] = pd.to_numeric(df['original_price'], errors='coerce')
        df['savings_pct'] = (((df['original_price'] - df['price']) / df['original_price']) * 100).fillna(0)
    else:
        df['savings_pct'] = 0.0

    if 'display_category' not in df.columns:
        df['display_category'] = df['category']
        
    return df

# --- ANALYSIS ENGINE ---
def get_item_stats(item_name, df):
    """Uses the FULL history for context."""
    history = df[df['item'].str.contains(item_name, case=False, regex=False)].copy()
    if history.empty: return None
    
    return {
        'avg': history['price'].mean(),
        'min': history['price'].min(),
        'count': len(history),
        'last_seen': history.sort_values('date', ascending=False).head(5)[['date', 'store', 'item', 'price']]
    }

def run_ai_analysis(item_row, stats):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(AI_MODEL_NAME)
    stats_text = f"Avg: ${stats['avg']:.2f}, Low: ${stats['min']:.2f}" if stats else "No history."
    prompt = f"Is this a good deal? Item: {item_row['item']} (${item_row['price']}) Stats: {stats_text}. 1 short sentence."
    try:
        return model.generate_content(prompt).text
    except:
        return "AI analysis unavailable."

# --- MAIN APP ---
def main():
    df_master = load_data() 
    today = pd.Timestamp.now().floor('D')

    if df_master.empty:
        st.error("No data found.")
        return

    # FLYER ISOLATION
    latest_dates = df_master.groupby('store')['date'].max().reset_index()
    latest_dates.columns = ['store', 'latest_flyer_date']
    df_current = pd.merge(df_master, latest_dates, on='store')
    df_current = df_current[df_current['date'] == df_current['latest_flyer_date']].copy()

    # Apply 7-day rule ONLY to current batch
    mask = df_current['valid_until'].isna()
    df_current.loc[mask, 'valid_until'] = df_current.loc[mask, 'date'] + timedelta(days=7)

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("🔍 Flyer Filters")
        show_history = st.toggle("Browse Historical Flyers", value=False)
        
        if not show_history:
            list_view_df = df_current[df_current['valid_until'] >= today].copy()
        else:
            list_view_df = df_master.copy()

        st.divider()
        sort_option = st.selectbox("Sort By", ["Expiring Soon", "Savings (High to Low)", "Price (Low to High)", "Alphabetical"])
        search_query = st.text_input("Search Flyer")
        
        cats = ["All"] + sorted(list_view_df['display_category'].dropna().unique().tolist())
        selected_cat = st.selectbox("Category", cats)
        
        if selected_cat != "All":
            list_view_df = list_view_df[list_view_df['display_category'] == selected_cat]

        sub_cats = sorted(list_view_df['sub_category'].dropna().unique().tolist())
        selected_sub = st.multiselect("Sub-Category", sub_cats)
        
        stores = sorted(list_view_df['store'].unique())
        store_filter = st.multiselect("Stores", stores, default=stores)

    # --- MAIN CONTENT ---
    st.title(f"🛒 {PAGE_TITLE}")
    tab_finder, tab_analyst = st.tabs(["🔎 Current Deals", "🤖 Ask Data"])

    # DEAL FINDER TAB
    with tab_finder:
        filtered_df = list_view_df.copy()
        if search_query:
            filtered_df = filtered_df[filtered_df['item'].str.contains(search_query, case=False, na=False)]
        if selected_sub:
            filtered_df = filtered_df[filtered_df['sub_category'].isin(selected_sub)]
        if store_filter:
            filtered_df = filtered_df[filtered_df['store'].isin(store_filter)]

        if filtered_df.empty:
            st.info("No active flyer deals match your filters.")
        else:
            # Sorting logic
            if sort_option == "Expiring Soon":
                filtered_df = filtered_df.sort_values(by='valid_until', ascending=True)
            elif sort_option == "Savings (High to Low)":
                filtered_df = filtered_df.sort_values(by='savings_pct', ascending=False)
            elif sort_option == "Price (Low to High)":
                filtered_df = filtered_df.sort_values(by='price', ascending=True)
            else:
                filtered_df = filtered_df.sort_values(by='item', ascending=True)

            for store in filtered_df['store'].unique():
                store_items = filtered_df[filtered_df['store'] == store]
                flyer_date = store_items['date'].iloc[0].strftime('%b %d')
                with st.expander(f"🏪 {store} (Flyer Date: {flyer_date})", expanded=True):
                    for _, row in store_items.iterrows():
                        c1, c2, c3 = st.columns([3, 1, 1])
                        valid_date = row['valid_until']
                        status_icon = "🟢" if valid_date >= today else "🔴"
                        date_str = f"Ends: {valid_date.strftime('%b %d')}"
                        
                        with c1:
                            st.write(f"**{row['item']}**")
                            st.caption(f"{status_icon} {date_str} | {row.get('sub_category','')}")
                        with c2:
                            st.markdown(f"**${row['price']:.2f}**" + (f" (🔥 {int(row['savings_pct'])}%)" if row['savings_pct'] > 0 else ""))
                        with c3:
                            if st.button("Analyze", key=f"btn_{row.name}"):
                                stats = get_item_stats(row['item'], df_master)
                                st.markdown("#### 📊 Historical Context")
                                if stats:
                                    delta = stats['avg'] - row['price']
                                    st.metric("Price vs. History Avg", f"${row['price']:.2f}", f"{delta:+.2f}", delta_color="inverse")
                                    st.dataframe(stats['last_seen'].style.format({"price": "${:.2f}"}), hide_index=True)
                                opinion = run_ai_analysis(row, stats)
                                st.success(f"🤖 {opinion}")
                                st.divider()

    # ASK DATA TAB (FULLY INTEGRATED)
    with tab_analyst:
        st.header("🤖 Flyer & History Analyst")
        st.caption(f"Context: {len(df_master)} total records (Historical) | {len(df_current)} current flyer items.")
        
        if "messages" not in st.session_state:
            st.session_state.messages = []
            
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                
        if prompt := st.chat_input("Ex: 'Compare current butter prices to last month'"):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.write(prompt)
            
            with st.chat_message("assistant"):
                with st.spinner("Analyzing master dataset..."):
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel(AI_MODEL_NAME)
                    
                    # We pass the MASTER data to the AI so it can see history
                    full_csv_context = df_master.to_csv(index=False)
                    today_str = today.strftime('%Y-%m-%d')
                    
                    ai_prompt = f"""
                    You are a Grocery Data Analyst for Calgary. 
                    TODAY IS: {today_str}.
                    
                    DATASET INFO:
                    - 'df_master' contains historical and current items.
                    - 'date' is when the item was scraped.
                    - 'valid_until' is when the deal expires.
                    
                    USER QUESTION: {prompt}
                    
                    INSTRUCTIONS:
                    1. If user asks for "now" or "current," prioritize rows where date is most recent.
                    2. If user asks for trends, use the whole history.
                    3. If graphing, use Plotly (px) and return code in ```python ``` blocks.
                    4. Reference stores specifically (Safeway, No Frills, etc.).
                    
                    CSV DATA:
                    {full_csv_context}
                    """
                    
                    try:
                        response = model.generate_content(ai_prompt).text
                        code_match = re.search(r"```python(.*?)```", response, re.DOTALL)
                        
                        if code_match:
                            code = code_match.group(1)
                            # Pass df_master as 'df' so the generated code works
                            local_vars = {"df": df_master, "px": px, "pd": pd}
                            exec(code, {}, local_vars)
                            if 'fig' in local_vars:
                                st.plotly_chart(local_vars['fig'])
                                st.session_state.messages.append({"role": "assistant", "content": "📊 *Analysis Chart Generated*"})
                        else:
                            st.write(response)
                            st.session_state.messages.append({"role": "assistant", "content": response})
                            
                    except Exception as e:
                        st.error(f"AI Error: {e}")

if __name__ == "__main__":
    main()