"""Robust student-input helper.

The harness is fundamentally interactive, but it must not hard-crash when
there is no attached terminal (headless / detached / "Run without console").

- With a real TTY (PowerShell, VS Code integrated terminal, a normal console):
  behaves exactly like input() and reads the student's keystrokes.
- Without a TTY (headless): reads the next line from a replies source and
  returns `default` (None) at EOF instead of raising, so callers can end the
  session gracefully.

Replies source priority when headless:
  1. TUTOR_REPLIES env var -> path to a file, one reply per line.
  2. Piped stdin (each line is one reply).
"""
import os
import sys

_REPLIES_FH = None


def is_interactive():
    """True only when stdin is a real terminal we can read keystrokes from."""
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:
        return False


def read_reply(prompt, default=None):
    """Read one line of student input.

    Returns `default` (None) at end-of-input instead of raising EOFError/OSError,
    so the caller can stop cleanly in headless mode.
    """
    if is_interactive():
        try:
            return input(prompt)
        except EOFError:
            return default

    # Headless: pull from a replies file or piped stdin, line by line.
    global _REPLIES_FH
    if _REPLIES_FH is None:
        path = os.environ.get("TUTOR_REPLIES")
        if path and os.path.exists(path):
            _REPLIES_FH = open(path, "r", encoding="utf-8")
        else:
            _REPLIES_FH = sys.stdin
    line = _REPLIES_FH.readline()
    if line == "":
        return default
    return line.rstrip("\n")
