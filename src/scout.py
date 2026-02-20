"""Scout Module: discovers non-competing micro-SaaS companies and saves them as leads.

Pipeline position: Stage 1 of 3
Input:  a natural-language profile description (e.g. "indie makers and solo developers")
Output: new rows in the companies table with status='scouted'

Design notes:
- Two complementary Tavily queries per profile maximise coverage diversity.
- Claude haiku extracts structured JSON (fast + cheap for high-volume extraction).
- Exponential back-off on every API call; silent per-result errors never abort the run.
- URL-level deduplication prevents re-scouting companies already in the pipeline.
"""

import json
import time
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError
from tavily import TavilyClient
import anthropic

from config import Config
from db import get_connection, insert_lead_if_new
from logger import get_logger

load_dotenv()
log = get_logger("scout")


class CompanyExtract(BaseModel):
    company_name: str = Field(description="Name of the company")
    url: str = Field(description="Canonical homepage URL of the company")
    contact_email: str | None = Field(description="Contact email, or null if not found")
    context_notes: str = Field(description="Background on the product and its target audience")


def _parse_json_from_response(text: str) -> dict:
    """Strip markdown fences if present and parse JSON."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        # parts[1] is between the first pair of fences
        text = parts[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def _extract_company(client: anthropic.Anthropic, result: dict, retries: int = 3) -> CompanyExtract | None:
    """Call Claude to extract structured company data from a Tavily search result.

    Returns a validated CompanyExtract on success, None after exhausting retries.
    """
    prompt = (
        f"Extract structured company data from this search result. "
        f"Return ONLY a JSON object — no markdown, no explanation.\n\n"
        f"Title:   {result.get('title', '')}\n"
        f"URL:     {result.get('url', '')}\n"
        f"Content: {result.get('content', '')}\n\n"
        f"Required JSON shape:\n"
        f'{{"company_name": "...", "url": "...", "contact_email": null, "context_notes": "..."}}\n'
        f"Use null for contact_email when not found. "
        f"url should be the canonical company homepage, not a blog post or docs page."
    )

    for attempt in range(retries):
        try:
            response = client.messages.create(
                model=Config.FAST_MODEL,
                max_tokens=512,
                system=(
                    "You are a precise data extraction assistant. "
                    "Respond only with valid JSON. No markdown code fences."
                ),
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text
            data = _parse_json_from_response(raw)
            return CompanyExtract.model_validate(data)

        except (json.JSONDecodeError, ValidationError) as e:
            log.warning(f"Parse error (attempt {attempt + 1}/{retries}): {e}")
            # No point retrying a deterministic parse error — break early
            return None

        except anthropic.APIStatusError as e:
            wait = 2 ** attempt
            log.warning(
                f"Anthropic API error {e.status_code} (attempt {attempt + 1}/{retries}). "
                f"Retrying in {wait}s."
            )
            time.sleep(wait)

        except anthropic.APIConnectionError as e:
            wait = 2 ** attempt
            log.warning(f"Connection error (attempt {attempt + 1}/{retries}): {e}. Retrying in {wait}s.")
            time.sleep(wait)

    return None


def scout_leads(profile_description: str, max_results: int | None = None) -> int:
    """Discover micro-SaaS companies matching *profile_description* and save to DB.

    Args:
        profile_description: Free-text description of the target audience/company type.
        max_results:         Results per Tavily query. Defaults to Config.SCOUT_MAX_RESULTS.

    Returns:
        Number of new leads inserted into the database.
    """
    Config.validate("ANTHROPIC_API_KEY", "TAVILY_API_KEY")

    if max_results is None:
        max_results = Config.SCOUT_MAX_RESULTS

    log.info(f"Scouting leads — profile: '{profile_description}', max_results={max_results}")

    tavily = TavilyClient(api_key=Config.TAVILY_API_KEY)
    claude = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    # Two complementary queries broaden coverage beyond a single search
    queries = [
        f"micro-SaaS tools {profile_description}",
        f"indie maker product {profile_description} newsletter",
    ]

    seen_urls: set[str] = set()  # dedup within this run (DB handles cross-run dedup)
    new_leads = 0

    conn = get_connection()
    cursor = conn.cursor()

    for query in queries:
        log.info(f"Tavily search: '{query}'")
        try:
            search_result = tavily.search(
                query=query,
                search_depth="advanced",
                max_results=max_results,
            )
        except Exception as e:
            log.error(f"Tavily search failed for '{query}': {e}")
            continue

        for result in search_result.get("results", []):
            result_url = result.get("url", "")
            if result_url in seen_urls:
                continue
            seen_urls.add(result_url)

            extract = _extract_company(claude, result)
            if extract is None:
                log.warning(f"Skipping {result_url}: could not extract structured data.")
                continue

            inserted = insert_lead_if_new(
                cursor,
                company_name=extract.company_name,
                url=extract.url,
                contact_email=extract.contact_email,
                context_notes=extract.context_notes,
            )
            if inserted:
                conn.commit()
                new_leads += 1
                log.info(f"  + New lead: {extract.company_name} <{extract.url}>")
            else:
                log.debug(f"  ~ Already in pipeline: {extract.url}")

    conn.close()
    log.info(f"Scouting complete. {new_leads} new lead(s) added.")
    return new_leads


if __name__ == "__main__":
    scout_leads("targeting indie makers and solo developers")
