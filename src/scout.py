import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from tavily import TavilyClient
import google.genai as genai
from db import get_connection

# Load secrets from .env file
load_dotenv()

class CompanyExtract(BaseModel):
    company_name: str = Field(description="Name of the company")
    url: str = Field(description="Website URL of the company")
    contact_email: str | None = Field(description="Contact email, or null if not found in context")
    context_notes: str = Field(description="Contextual background information and what the tool does")

def scout_leads(profile_description: str):
    """Search for non-competing micro-SaaS companies matching the profile and save to DB."""
    tavily_api_key = os.environ.get("TAVILY_API_KEY")
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    
    if not tavily_api_key or not gemini_api_key:
        print("Missing API keys. Ensure TAVILY_API_KEY and GEMINI_API_KEY are set.")
        return

    # 1. Search via Tavily
    print(f"Searching Tavily for matching profiles: {profile_description}")
    tclient = TavilyClient(api_key=tavily_api_key)
    search_result = tclient.search(
        query=f"micro-SaaS tools {profile_description}", 
        search_depth="advanced", 
        max_results=5
    )
    
    # 2. Extract using Gemini structured outputs
    client = genai.Client(api_key=gemini_api_key)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    for result in search_result.get("results", []):
        prompt = (
            f"Extract company details from the following search result.\n"
            f"Title: {result.get('title')}\n"
            f"Content: {result.get('content')}\n"
            f"URL: {result.get('url')}\n\n"
            f"Return the requested JSON fields. Be sure to extract the company name accurately."
        )
        
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CompanyExtract,
                ),
            )
            
            extract = CompanyExtract.model_validate_json(response.text)
            print(f"Discovered: {extract.company_name} - {extract.url}")
            
            # Insert lead into DB
            cursor.execute('''
                INSERT INTO companies (company_name, url, contact_email, status, context_notes)
                VALUES (?, ?, ?, 'scouted', ?)
            ''', (extract.company_name, extract.url, extract.contact_email, extract.context_notes))
            conn.commit()
            
        except Exception as e:
            print(f"Error parsing or inserting lead from URL {result.get('url')}: {e}")
            
    conn.close()
    print("Scouting complete.")

if __name__ == "__main__":
    scout_leads("targeting indie makers and solo developers")
