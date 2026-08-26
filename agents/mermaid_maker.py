import os
from config import MODEL, get_client
from extensions.cache_store import cache_get, cache_set

def generate_mermaid_dag(topic: str, prerequisite_summary: str = "Baseline") -> str:
    """Generate Mermaid `graph TD` code for the lesson path given `topic` and a `prerequisite_summary`. Returns raw Mermaid code (no fences)."""
    cache_key = f"{topic}|{prerequisite_summary}"
    cached = cache_get("mermaid", cache_key)
    if cached is not None:
        return cached
    try:
        client = get_client()
        prompt = f"""
Create a detailed prerequisite learning path for topic: '{topic}'.
User Knowledge Baseline: {prerequisite_summary}

Return ONLY valid Mermaid.js graph code (graph TD). 
Do NOT wrap in markdown backticks.
Keep node text short and granular.
"""
        from google.genai import types
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2),
        )
        text = (response.text or "").strip()
        if text.startswith("```mermaid"):
            text = text.replace("```mermaid", "").replace("```", "").strip()
        elif text.startswith("```"):
            text = text.replace("```", "").strip()
        if not text:
            return "graph TD\n    Node[No DAG generated]"
        cache_set("mermaid", cache_key, text)
        return text
    except Exception as e:
        return f"graph TD\n    Error[Mermaid Generation Error: {str(e)}]"