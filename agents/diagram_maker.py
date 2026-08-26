import os
import sys
import json
import uuid
import struct
import tempfile
import subprocess

from google import genai
from google.genai import types
from config import MODEL, get_client
from extensions.md_log import get_obsidian_path

# Secrets that must NEVER be visible to the LLM-generated plotting code.
_SECRET_KEYS = (
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
    "AZURE_OPENAI_API_KEY", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN",
)

# How many times to (re)generate the diagram when self-verification fails.
_MAX_VERIFY_ATTEMPTS = 2


def _safe_env():
    """Return a copy of the environment with secret keys stripped out.

    The plotting subprocess only needs matplotlib/numpy, never our API
    credentials. Passing this (instead of inheriting os.environ) prevents
    LLM-generated code from reading or exfiltrating our secrets.
    """
    env = dict(os.environ)
    for key in _SECRET_KEYS:
        env.pop(key, None)
    return env


def _resolve_attachment_dir():
    """Locate the Obsidian attachment folder for the active vault.

    Walks up from the active note path to find the vault root (the
    directory containing `.obsidian`), then resolves Obsidian's
    configured attachment folder (defaults to `Attachments`). Returns
    a tuple of (attachment_dir, base_dir) where base_dir is the
    vault root (used to compute the Obsidian-relative embed path).
    Never raises; falls back to a temp dir if nothing can be found.
    """
    note_path = None
    try:
        note_path = get_obsidian_path()
    except Exception:
        note_path = None

    vault_root = None
    if note_path and os.path.exists(note_path):
        cur = os.path.dirname(note_path)
        while True:
            if os.path.isdir(os.path.join(cur, ".obsidian")):
                vault_root = cur
                break
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent

    attachment_rel = "Attachments"
    if vault_root:
        try:
            with open(os.path.join(vault_root, ".obsidian", "app.json"),
                      "r", encoding="utf-8") as f:
                cfg = json.load(f)
            afp = cfg.get("attachmentFolderPath")
            if afp:
                attachment_rel = afp
        except Exception:
            pass

    if vault_root:
        base_dir = vault_root
        attachment_dir = os.path.join(vault_root, attachment_rel)
    elif note_path:
        base_dir = os.path.dirname(note_path)
        attachment_dir = os.path.join(base_dir, attachment_rel)
    else:
        base_dir = tempfile.gettempdir()
        attachment_dir = os.path.join(base_dir, "obsidian_attachments")

    os.makedirs(attachment_dir, exist_ok=True)
    return attachment_dir, base_dir


def _call_model_for_code(concept: str, feedback: str = "", attempt: int = 1) -> str:
    """Ask Gemini to write self-contained matplotlib plotting code."""
    feedback_block = ""
    if feedback:
        feedback_block = (
            f"\nThe previous attempt FAILED self-verification with these issues: "
            f"{feedback}\nFix them explicitly in this retry. "
        )

    prompt = f"""
You are a scientific visualization expert. Write a single self-contained
Python script that renders a clear, mathematically correct diagram
illustrating the concept: '{concept}'.{feedback_block}

STRICT REQUIREMENTS:
- Use ONLY the `matplotlib` library (and `numpy` if needed).
- The script MUST save the figure to the file path already provided in
  the variable `OUTPUT_PATH`. Use exactly:
      fig.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight")
- The non-interactive Agg backend is already configured. Do NOT call
  plt.show(). Do NOT use input(), open(), or any network access.
- Make the figure readable: titles, axis labels, and legends where relevant.
- Return ONLY raw Python code with no markdown fences and no commentary.
""".strip()

    response = get_client().models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2),
    )
    code = (response.text or "").strip()

    # Strip accidental markdown fences.
    if code.startswith("```"):
        code = code.split("\n", 1)[1] if "\n" in code else ""
    if code.endswith("```"):
        code = code.rsplit("```", 1)[0]
    return code.strip()


def _png_dimensions(path: str):
    """Read width/height from a PNG IHDR chunk without external deps.

    Returns (w, h) on success, or None if the file is not a valid PNG.
    """
    try:
        with open(path, "rb") as f:
            sig = f.read(8)
            if sig != b"\x89PNG\r\n\x1a\n":
                return None
            f.read(4)  # chunk length
            if f.read(4) != b"IHDR":
                return None
            return struct.unpack(">II", f.read(8))
    except Exception:
        return None


def _vision_verify(path: str, concept: str):
    """Send the rendered PNG to Gemini for a strict correctness review.

    Returns (valid, correct, issues). On any failure we are lenient (treat as
    valid/correct) so an unavailable reviewer never blocks a genuinely good
    diagram, but we surface the reason.
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
        prompt = (
            "You are a strict scientific diagram reviewer. The intended concept "
            f"was: '{concept}'. Examine the attached image and judge: "
            "(1) is it a valid, non-blank rendered figure, "
            "(2) does it correctly and clearly illustrate the stated concept, "
            "(3) any obvious errors (blank axes, missing labels, wrong math, "
            "cut-off text, irrelevant content). "
            "Respond with ONLY a JSON object: "
            '{"valid": true/false, "correct": true/false, "issues": "short description"}'
        )
        resp = get_client().models.generate_content(
            model=MODEL,
            contents=[prompt, types.Part.from_bytes(data=data, mime_type="image/png")],
            config=types.GenerateContentConfig(temperature=0.2),
        )
        text = (resp.text or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            return True, True, "reviewer returned no parseable JSON"
        parsed = json.loads(text[start:end + 1])
        valid = bool(parsed.get("valid", True))
        correct = bool(parsed.get("correct", True))
        issues = str(parsed.get("issues", "")).strip()
        return valid, correct, issues
    except Exception as e:
        return True, True, f"verification skipped ({e})"


def _verify_diagram(path: str, concept: str):
    """Validate that the saved PNG is a real, correct diagram.

    Combines a cheap structural check (valid PNG, sane dimensions, non-trivial
    size) with a Gemini vision review. Returns (ok, issues).
    """
    if not os.path.isfile(path):
        return False, "PNG file was not created."

    dims = _png_dimensions(path)
    if dims is None:
        return False, "output is not a valid PNG image."
    if dims[0] <= 0 or dims[1] <= 0:
        return False, "image has zero width or height."

    size = os.path.getsize(path)
    if size < 1500:
        return False, f"image is suspiciously small ({size} bytes) — likely blank."

    valid, correct, issues = _vision_verify(path, concept)
    if not valid:
        return False, f"reviewer: not a valid figure ({issues})"
    if not correct:
        return False, f"reviewer: does not correctly illustrate concept ({issues})"
    return True, issues


def _run_plotting_code(full_code: str):
    """Execute LLM-generated plotting code in a hermetic subprocess."""
    tmp_py = os.path.join(tempfile.gettempdir(), f"diagram_{uuid.uuid4().hex[:12]}.py")
    try:
        with open(tmp_py, "w", encoding="utf-8") as f:
            f.write(full_code)

        proc = subprocess.run(
            [sys.executable, tmp_py],
            capture_output=True,
            text=True,
            timeout=90,
            env=_safe_env(),
            cwd=tempfile.gettempdir(),
        )
    except subprocess.TimeoutExpired:
        return None, "Diagram generation failed: plotting code timed out."
    except Exception as e:
        return None, f"Diagram generation failed (execution error): {str(e)}"
    finally:
        try:
            os.remove(tmp_py)
        except Exception:
            pass

    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        last_line = stderr.splitlines()[-1] if stderr else "no output produced"
        if "ModuleNotFoundError" in stderr and "matplotlib" in stderr:
            return None, ("Diagram generation failed: the `matplotlib` library "
                          "is not installed. Run `pip install matplotlib numpy` "
                          "and try again.")
        return None, f"Diagram generation failed: {last_line}"
    return proc, None


def generate_diagram(concept: str) -> str:
    """Render a self-verified, mathematically correct diagram for `concept`.

    Asks Gemini to write self-contained Python (matplotlib) plotting code,
    executes it in an isolated subprocess, saves the result as a .png into the
    Obsidian attachment folder, then SELF-VERIFIES the image is valid and
    correctly depicts the concept. On failure it retries with the reviewer's
    feedback. Returns an Obsidian image embed (`![[...]]`) on success, a
    warning-embed if verification could not confirm correctness, or a plain
    error string on hard failure (so the tutor can continue without crashing).
    """
    attachment_dir, base_dir = _resolve_attachment_dir()
    filename = f"diagram_{uuid.uuid4().hex[:12]}.png"
    output_path = os.path.join(attachment_dir, filename)

    header = (
        "import os\n"
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n"
        "import numpy as np\n"
        f"OUTPUT_PATH = r'{output_path}'\n"
    )

    last_issues = ""
    for attempt in range(1, _MAX_VERIFY_ATTEMPTS + 1):
        code = _call_model_for_code(concept, last_issues, attempt)
        if not code:
            return "Diagram generation failed: model returned no code."

        full_code = header + "\n" + code
        proc, err = _run_plotting_code(full_code)
        if err:
            # Hard execution failure (e.g. matplotlib missing) — do not retry;
            # the environment issue will persist across attempts.
            return err

        if not os.path.isfile(output_path):
            last_issues = "PNG not produced by plotting code"
            continue

        ok, issues = _verify_diagram(output_path, concept)
        if ok:
            rel = os.path.relpath(output_path, base_dir).replace(os.sep, "/")
            embed = f"![[{rel}]]"
            # Be honest: if the vision reviewer couldn't actually run (no
            # multimodal model, or it returned no parseable verdict), only
            # structural checks passed — say so instead of claiming verified.
            if issues and ("skipped" in issues or "no parseable" in issues):
                embed += (
                    f"\n\n> ⚠️ Diagram self-verification could NOT be fully run "
                    f"({issues}); only structural checks (valid PNG, non-blank) "
                    f"passed. Confirm correctness manually."
                )
            return embed

        # Verification failed: remove the bad image and retry with feedback.
        try:
            os.remove(output_path)
        except Exception:
            pass
        last_issues = issues or f"self-verification failed (attempt {attempt})"

    # Exhausted retries. Return a warning-embed so the note flags the problem
    # instead of silently shipping a broken diagram.
    if os.path.isfile(output_path):
        rel = os.path.relpath(output_path, base_dir).replace(os.sep, "/")
        warn = (f"\n\n> ⚠️ Diagram self-verification could not confirm this image "
                f"correctly illustrates '{concept}'. Issues: {last_issues}")
        return f"![[{rel}]]{warn}"

    return f"Diagram generation failed: self-verification repeated failed ({last_issues})."
