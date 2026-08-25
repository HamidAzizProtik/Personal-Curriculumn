import os
from google import genai

def research_topic(query: str) -> str:
    """Sub-agent: Gathers technical background and prerequisite concepts."""
    try:
        client = genai.Client()
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=f"Provide a concise technical breakdown, core concepts, and edge cases for: {query}"
        )
        text = response.text or ""
        return text.strip() if text else "No research response content returned."
    except Exception as e:
        return f"Research error: {str(e)}"