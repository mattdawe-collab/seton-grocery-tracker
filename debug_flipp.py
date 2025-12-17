import os
from dotenv import load_dotenv
from supabase import create_client, Client

# --- CONFIGURATION ---
# 1. LOAD SECRETS
load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

# 2. DEFINE YOUR TABLE NAME
# Change this to 'grocery_deals' or 'deal_scans' if you used those names instead!
TABLE_NAME = "price_reports" 

# --- MAIN CHECK ---
def run_diagnostic():
    print(f"1. Checking Credentials...")
    if not url or not key:
        print("❌ FAILED: Missing .env keys (SUPABASE_URL or SUPABASE_KEY).")
        return
    print(f"   ✅ Keys found.")

    print(f"2. Connecting to Supabase...")
    try:
        supabase: Client = create_client(url, key)
        print(f"   ✅ Connection object created.")
    except Exception as e:
        print(f"❌ FAILED: Could not connect. Error: {e}")
        return

    print(f"3. Testing WRITE permission (Inserting dummy row)...")
    dummy_data = {
        "product_name": "TEST_CONNECTION_ITEM",
        "price": 0.99,
        "store_name": "DEBUG_STORE"
    }
    
    try:
        # We insert and ask for the data back ('select()') to confirm it worked
        insert_response = supabase.table(TABLE_NAME).insert(dummy_data).execute()
        print(f"   ✅ Success! Inserted row ID: {insert_response.data[0]['id']}")
    except Exception as e:
        print(f"❌ FAILED: Write error. Does table '{TABLE_NAME}' exist?")
        print(f"   Error Details: {e}")
        return

    print(f"4. Testing READ permission (Fetching dummy row)...")
    try:
        # Fetch the item we just created
        read_response = supabase.table(TABLE_NAME).select("*").eq("product_name", "TEST_CONNECTION_ITEM").execute()
        
        if len(read_response.data) > 0:
            print(f"   ✅ Success! Read back: {read_response.data[0]['product_name']}")
            
            # (Optional) Verify Columns exist
            row = read_response.data[0]
            expected_cols = ["product_name", "price", "store_name", "reported_at"]
            missing = [col for col in expected_cols if col not in row]
            
            if not missing:
                print(f"   ✅ Schema Check: All critical columns found.")
            else:
                print(f"   ⚠️ WARNING: Missing columns in table: {missing}")
                
        else:
            print("❌ FAILED: Inserted row was not found.")
            return
    except Exception as e:
        print(f"❌ FAILED: Read error: {e}")
        return

    print(f"5. Cleaning up...")
    try:
        # Delete the test row so it doesn't mess up your app
        supabase.table(TABLE_NAME).delete().eq("product_name", "TEST_CONNECTION_ITEM").execute()
        print("   ✅ Test data deleted.")
    except Exception as e:
        print(f"   ⚠️ Could not delete test data: {e}")

    print("\n🎉 DIAGNOSTIC COMPLETE: System is GO for launch.")

if __name__ == "__main__":
    run_diagnostic()