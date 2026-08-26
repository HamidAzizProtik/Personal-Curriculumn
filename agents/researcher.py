import os
from google import genai
from google.genai import types

from config import MODEL, get_client
from extensions.cache_store import cache_get, cache_set

# In-session cache so repeated/re-phrased research queries don't re-hit the API.
_CACHE = {}


def _make_search_tool():
    """Build a Google Search grounding tool, or None if unsupported."""
    try:
        return types.Tool(google_search=types.GoogleSearch())
    except Exception:
        return None


def _extract_citations(response):
    """Pull web sources out of Gemini grounding metadata, de-duplicated."""
    cites = []
    try:
        gm = response.candidates[0].grounding_metadata
        for chunk in getattr(gm, "grounding_chunks", []) or []:
            web = getattr(chunk, "web", None)
            if web and getattr(web, "uri", None):
                title = (getattr(web, "title", "") or "").strip()
                cites.append(f"{title} — {web.uri}" if title else web.uri)
    except Exception:
        pass
    seen, out = set(), []
    for c in cites:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def research_topic(query: str, grounded: bool = True) -> str:
    """Gather reliable, cited background on `query` (Google Search grounding when available). Returns text plus a 'Sources:' block; results are cached per query."""
    cache_key = (query, grounded)
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    disk = cache_get("research", f"{query}|{grounded}")
    if disk is not None:
        _CACHE[cache_key] = disk
        return disk

    try:
        client = get_client()
    except Exception as e:
        return f"Research error: {str(e)}"

    prompt = (
        f"Produce a rigorous, technically precise briefing on: {query}.\n"
        f"Prioritize established, verifiable facts. Distinguish well-known "
        f"results from contested or nuanced points. Avoid speculation. "
        f"If sources are available, ground every non-trivial claim in them."
    )

    configs = []
    if grounded:
        tool = _make_search_tool()
        if tool:
            try:
                configs.append(types.GenerateContentConfig(tools=[tool], temperature=0.2))
            except Exception:
                pass
    configs.append(types.GenerateContentConfig(temperature=0.2))  # fallback: no grounding

    response = None
    err = None
    for cfg in configs:
        try:
            response = client.models.generate_content(
                model=MODEL, contents=prompt, config=cfg
            )
            break
        except Exception as e:
            err = e
            continue

    if response is None:
        return f"Research error: {str(err)}"

    text = (response.text or "").strip()
    if not text:
        return "No research response content returned."

    cites = _extract_citations(response)
    if cites:
        header = "\n\n**Sources (grounded):**" if "**" in text else "\n\nSources:"
        text += header + "\n" + "\n".join(f"- {c}" for c in cites)
    else:
        # Honest signal so notes don't imply false authority.
        text += "\n\n(No external sources grounded for this query.)"

    _CACHE[cache_key] = text
    cache_set("research", f"{query}|{grounded}", text)
    return text
