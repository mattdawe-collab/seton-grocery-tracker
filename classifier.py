import os
from dotenv import load_dotenv # <--- LOADS YOUR .ENV FILE
from pydantic import BaseModel, Field
from google import genai
from typing import List, Literal

# Load environment variables (API Key)
load_dotenv()

# 1. Define your strict categories
CategoryType = Literal[
    "Produce", 
    "Meat & Seafood", 
    "Dairy & Eggs", 
    "Bakery", 
    "Pantry", 
    "Frozen", 
    "Beverages", 
    "Household & Personal", 
    "Snacks",
    "Other"
]

# 2. Define the exact structure (The "Shape")
class GroceryItem(BaseModel):
    original_name: str = Field(description="The name exactly as it appeared in the flyer")
    clean_name: str = Field(description="A short, clean name for display (e.g. 'Gala Apples' instead of 'Apples Gala 3lb bag')")
    category: CategoryType
    is_deal: bool = Field(description="True if this looks like a significant sale/doorcrasher based on the name")

class GroceryList(BaseModel):
    items: List[GroceryItem]

# 3. The Classification Function
def categorize_groceries(raw_items: List[str]):
    # This now grabs the key securely from your .env file
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found. Make sure you created the .env file.")

    client = genai.Client(api_key=api_key)

    prompt = f"""
    You are a grocery data assistant for a database. 
    Analyze the following list of raw flyer items and categorize them strictly.
    Clean up the names for better UI display (remove weights/pack sizes from the name).
    
    Raw Items:
    {raw_items}
    """

    response = client.models.generate_content(
        model="gemini-2.0-flash", 
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": GroceryList,
        },
    )

    return response.parsed.items