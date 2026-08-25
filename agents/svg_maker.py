import os
from google import genai

def generate_svg_diagram(concept: str) -> str:
    """Sub-agent: Generates self-contained vector SVG diagrams."""
    try:
        client = genai.Client()
        prompt = f"""
Generate a clean, self-contained SVG visual diagram illustrating: '{concept}'.
Use high contrast colors compatible with dark mode, and explicit labels.
Return ONLY valid <svg>...</svg> XML markup without markdown code fences.
"""
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt
        )
        text = (response.text or "").strip()
        if text.startswith("```xml") or text.startswith("```html"):
            text = text.split("\n", 1)[1].rsplit("\n", 1)[0].strip()
        elif text.startswith("```"):
            text = text.replace("```", "").strip()
        return text if text else '<svg width="300" height="100"><text x="10" y="50" fill="red">No SVG content generated</text></svg>'
    except Exception as e:
        return f'<svg width="300" height="100"><text x="10" y="50" fill="red">SVG Error: {str(e)}</text></svg>'