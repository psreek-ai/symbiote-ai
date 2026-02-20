# Symbiote AI

**Symbiote AI** is a headless, multi-agent business development system. Its core functionality is to autonomously scout non-competing micro-SaaS companies, negotiate newsletter or widget cross-promotions via personalized emails, and visually verify the placement of partnership links dynamically.

## Architecture

The system coordinates several distinct parallel agents through a shared local SQLite database (`leads.db`):

1. **Scout Module (`src/scout.py`)**: Uses Tavily for deep web searches based on target business profiles, then parses the search results using Gemini to extract key company information into the database as a "scouted" lead.
2. **Negotiate Module (`src/negotiate.py`)**: Pulls scouted leads and generates highly personalized, 3-sentence outreach emails proposing a 1-to-1 audience swap, strictly forbidding any financial offerings. Sends outreach via Resend.
3. **Verify Module (`src/verify.py`)**: Utilizes an autonomous Browser Agent (Antigravity architecture) to visit partner URLs, parse the DOM and visual canvas, and identify if the negotiated widget/link has been actively placed.

## Prerequisites

- Python 3.11+
- The following API keys:
  - **Tavily API**: For deep web search capabilities.
  - **Google Gemini API**: For extracting intent, details, and generating personalized emails.
  - **Resend API**: For dispatching outbound email negotiations.

## Setup Instructions

1. **Clone the repository** (or navigate to your local working directory).
2. **Set up a Virtual Environment**:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```
3. **Install Dependencies**:
   ```bash
   pip install pydantic anthropic google-genai tavily-python resend pytest python-dotenv
   ```
4. **Configure Environment Variables**:
   Open the `.env` file generated in the project root (or copy `.env.example` to `.env`) and add your required keys:
   ```env
   TAVILY_API_KEY=your_key_here
   GEMINI_API_KEY=your_key_here
   RESEND_API_KEY=your_key_here
   ```
5. **Initialize the Database**:
   Run the database initialization script to create the local `leads.db` SQLite database with the necessary tables constraints.
   ```bash
   python src/db.py
   ```

## Usage

You can trigger the independent agents by executing their respective scripts in the background or via cron jobs:

- **Scout Leads:**
  ```bash
  python src/scout.py
  ```
- **Draft and Send Negotiation Campaigns:**
  *(Note: Run in safe/dry-run mode until you confirm the API responses are working as expected!)*
  ```bash
  python src/negotiate.py
  ```
- **Visually Verify Executed Partnerships:**
  ```bash
  python src/verify.py
  ```
