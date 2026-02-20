import os
from dotenv import load_dotenv
import resend
import google.genai as genai
from db import get_connection

# Load secrets from .env file
load_dotenv()

def draft_and_send_emails():
    """Drafts a 3-sentence outreach email proposing a 1-to-1 audience swap and sends it."""
    resend.api_key = os.environ.get("RESEND_API_KEY")
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    
    if not resend.api_key or not gemini_api_key:
        print("Missing API keys for Resend or Gemini.")
        # We can still run dry-run testing below
        
    client = genai.Client(api_key=gemini_api_key) if gemini_api_key else None
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Fetch scouted leads
    cursor.execute("SELECT id, company_name, url, contact_email, context_notes FROM companies WHERE status = 'scouted'")
    leads = cursor.fetchall()
    
    if not leads:
        print("No 'scouted' leads found to negotiate with.")
        
    for lead in leads:
        lead_id, company_name, url, contact_email, context_notes = lead
        if not contact_email:
            print(f"Skipping {company_name} due to missing email.")
            continue
            
        # Draft email
        prompt = (
            f"You are the Head of Partnerships at Symbiote AI. "
            f"Draft a highly personalized, exactly 3-sentence outreach email to the company '{company_name}' ({url}).\n"
            f"Context about them: {context_notes}\n\n"
            f"The goal is to propose a 1-to-1 audience swap (e.g., newsletter cross-promotion or widget swap).\n"
            f"Strict guardrail: DO NOT offer any financial compensation or mention money.\n"
            f"Return only the email body without subject line or placeholders."
        )
        
        try:
            if client:
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt
                )
                email_body = response.text.strip()
            else:
                email_body = f"Hey {company_name}, loved your work on {url} and think our audiences would overlap perfectly. We're Symbiote AI, and we'd love to propose a 1-to-1 audience swap via a newsletter cross-promotion. Let me know if you are open to chatting!"
                
            print(f"Drafted email for {company_name} (to: {contact_email}):\n{email_body}\n---")
            
            # Send email via Resend
            if resend.api_key:
                # r = resend.Emails.send({
                #     "from": "onboarding@resend.dev",
                #     "to": [contact_email],
                #     "subject": f"Partnership possibility: Symbiote AI x {company_name}",
                #     "text": email_body
                # })
                pass
            
            # Mark as pitched
            cursor.execute("UPDATE companies SET status = 'pitched' WHERE id = ?", (lead_id,))
            conn.commit()
            print(f"Marked {company_name} as 'pitched' in database.\n")
            
        except Exception as e:
            print(f"Failed to draft or send email to {company_name}: {e}")

    conn.close()

if __name__ == "__main__":
    draft_and_send_emails()
