import os
from google import genai

def generate_mermaid_dag(topic: str, prerequisite_summary: str = "Baseline") -> str:
    """Sub-agent: Generates clean Mermaid.js graph TD code for learning paths."""
    try:
        client = genai.Client()
        prompt = f"""
Create a detailed prerequisite learning path for topic: '{topic}'.
User Knowledge Baseline: {prerequisite_summary}

Return ONLY valid Mermaid.js graph code (graph TD). 
Do NOT wrap in markdown backticks.
Keep node text short and granular.
"""
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt
        )
        text = (response.text or "").strip()
        if text.startswith("```mermaid"):
            text = text.replace("```mermaid", "").replace("```", "").strip()
        elif text.startswith("```"):
            text = text.replace("```", "").strip()
        return text if text else "graph TD\n    Node[No DAG generated]"
    except Exception as e:
        return f"graph TD\n    Error[Mermaid Generation Error: {str(e)}]"