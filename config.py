import os

# Central model selection.
# Override at runtime without editing code:
#   Windows (cmd):  set GEMINI_MODEL=gemini-3.6-flash
#   PowerShell:      $env:GEMINI_MODEL="gemini-3.6-flash"
#   bash:           export GEMINI_MODEL=gemini-3.6-flash
#
# NOTE: grounded research/verification (researcher.py) requires a
# search-capable model. If GEMINI_MODEL is set to a model that does not
# support Google Search grounding, researcher.py automatically falls back
# to ungrounded generation and reports that citations are unavailable.

# Models that are deprecated / unavailable to new users. If one is selected
# (e.g. via a stale GEMINI_MODEL env var), we transparently remap to the
# current default so the whole harness runs on a supported model.
_DEPRECATED_MODELS = {
    "gemini-2.5-flash", "gemini-2.5-flash-latest",
    "gemini-2.5-pro", "gemini-2.5-pro-latest",
}
_raw_model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
if _raw_model in _DEPRECATED_MODELS:
    print(f"[config] Model '{_raw_model}' is deprecated/unavailable for new "
          f"users; using 'gemini-3.6-flash' instead.")
    _raw_model = "gemini-3.6-flash"
MODEL = _raw_model

VERSION = "1.0.0"

# One lazily-created, reused client for all sub-agents. Reusing a single
# client avoids repeated TLS handshakes / construction overhead on every
# tool call (a real, quality-neutral speed win). Imported lazily so this
# module loads even where the SDK is absent.
_client = None


def get_client():
    """Return a shared genai.Client with a sane request timeout."""
    global _client
    if _client is None:
        from google import genai
        from google.genai import types
        _client = genai.Client(http_options=types.HttpOptions(timeout=120000))
    return _client

