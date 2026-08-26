"""Rate-limit resilience for the Gemini free tier.

Two mechanisms, shared across the whole harness (tutor turns AND research calls):

* ``pace()``  -- enforces a minimum gap between *every* model API call so we stay
                 safely under the free-tier RPM instead of crashing into it.
* ``with_retry`` / inline retry in ``main.py`` -- on a 429/5xx the call backs off
                 and retries instead of killing the session.

All failures degrade gracefully: if pacing/retry can't help (a hard 4xx), the
exception propagates exactly as before, so no feature behavior changes.
"""
import os
import time
import re

# Free-tier Gemini Flash is roughly ~10 RPM. A 6s floor keeps us comfortably
# under that even when tutor turns and research calls interleave. Tune with the
# TUTOR_MIN_INTERVAL env var (seconds) if you have a higher quota.
MIN_INTERVAL = float(os.environ.get("TUTOR_MIN_INTERVAL", "6.0"))

# Backoff schedule for rate-limit retries.
BACKOFF_BASE = 5.0
BACKOFF_FACTOR = 2.0
MAX_RETRIES = 6

_last_call = 0.0


def pace():
    """Block just long enough to keep all model calls >= MIN_INTERVAL apart."""
    global _last_call
    now = time.monotonic()
    wait = MIN_INTERVAL - (now - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _is_rate_limit(err):
    code = getattr(err, "code", None)
    if code in (429, 500, 503):
        return True
    msg = (getattr(err, "message", "") or str(err)).lower()
    return any(t in msg for t in ("rate", "quota", "429", "503", "resource exhausted"))


def _retry_after(err):
    """Best-effort extraction of a server-suggested wait (seconds)."""
    try:
        msg = getattr(err, "message", "") or str(err)
    except Exception:
        return None
    m = re.search(r"retry[_\s-]?after[:\s]+(\d+)", msg, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"retry_delay[^0-9]*(\d+)", msg, re.I)
    if m:
        return float(m.group(1))
    det = getattr(err, "details", None)
    if isinstance(det, list):
        for d in det:
            rd = getattr(d, "retry_delay", None)
            if not rd and isinstance(d, dict):
                rd = d.get("retryDelay")
            if rd:
                try:
                    return float(str(rd).rstrip("s"))
                except Exception:
                    pass
    return None


def with_retry(fn, *args, max_retries=MAX_RETRIES, **kwargs):
    """Call ``fn``; on a transient rate-limit/5xx, back off and retry."""
    delay = BACKOFF_BASE
    for attempt in range(max_retries + 1):
        try:
            pace()
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt >= max_retries or not _is_rate_limit(e):
                raise
            ra = _retry_after(e)
            sleep_for = ra if ra else delay
            print(f"[Rate limit] backing off {sleep_for:.0f}s "
                  f"(attempt {attempt + 1}/{max_retries})")
            time.sleep(sleep_for)
            delay *= BACKOFF_FACTOR
