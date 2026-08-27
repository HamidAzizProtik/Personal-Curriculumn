# AI Tutor

A one-to-one AI tutor that runs a strict, pedagogically-grounded teaching loop:
it **probes** your prerequisites, **plans** a lesson DAG, then **teaches** one
node at a time with mandatory fact-checking, diagrams, and drills. It runs on
Gemini and persists a learner model across sessions so you start warm.

> ⚠️ **SECURITY WARNING — arbitrary code execution.**
> The diagram feature (`generate_diagram`) runs **LLM-generated Python
> (matplotlib) code on your machine**, exactly as written by the model. Treat
> model output as untrusted.
>
> The harness only protects **secret environment variables** — they are stripped
> from the subprocess environment (`agents/diagram_maker.py:32`), so generated
> code cannot read `GEMINI_API_KEY` etc. from the process environment. **That is
> the only protection.** Generated code still has full access to your
> filesystem and can read, overwrite, or delete any file your user account can
> reach (e.g. `~/.ssh`, documents), and could attempt network exfiltration. The
> prompt asks the model not to use `open()`/network, but the model is not
> forced to comply.
>
> **Do not run the diagram agent on a machine with data you care about** unless
> you sandbox it (dedicated limited user, no network, container/VM). The diagram
> feature is opt-in — it only runs if the tutor decides to call
> `generate_diagram`; you can avoid it entirely by ignoring/refusing diagram
> requests during a session.

## Prerequisites
- Python 3.11+
- A Gemini API key (https://aistudio.google.com/apikey)

## API key & secrets (you never edit code)
Your key is **never hardcoded** in this project. It is read at runtime from a
local `api.env` file (git-ignored) or the `GEMINI_API_KEY` environment variable.
To set it up:

1. Copy the template: `api.env.example` → `api.env`.
2. Put your key in `api.env` as `GEMINI_API_KEY=your_key_here`.

`api.env` is excluded by `.gitignore`, so it will not be committed. **Before
publishing, verify it is ignored:**

```bash
git check-ignore api.env   # should print: api.env
```

If that prints nothing, do **not** push — your key would be exposed. Rotate the
key immediately if it was ever committed, because `.gitignore` does **not**
scrub git history.

## Install
Works the same on Windows / macOS / Linux:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

Or use the helper: `init.bat` (Windows) / `init.sh` (macOS, Linux).

## Setup (required before first run)
1. **API key.** Copy `api.env.example` to `api.env` and insert your key:
   ```
   GEMINI_API_KEY=your_key_here
   ```
2. **Note file.** Create `vault_path.txt` in the project root containing the
   absolute path to the Obsidian note you want lessons appended to, e.g.:
   ```
   C:\Users\you\Obsidian\vault\learning\lesson.md
   ```
   The diagram attachment folder is auto-detected from your vault's
   `.obsidian/app.json` (defaults to `Attachments`).

## Run
```bash
python main.py "mental math: fast addition and subtraction"
```
Answer the probe/quiz prompts naturally. `exit` / `quit` ends the session.
Add `--resume "<topic>"` to continue a throttled or interrupted session.

## Choosing a model
Default model is `gemini-3.6-flash`. Override it with the `GEMINI_MODEL` env
var (e.g. `set GEMINI_MODEL=gemini-2.5-flash` / `export GEMINI_MODEL=...`).
Use a model your Gemini account can actually access — if a run fails with a
model error, set `GEMINI_MODEL` to one available to you.

> **Note for distributors:** the default model string must be one that exists
> and is enabled for the end user's account. If it is not, the very first API
> call fails. Tell users to set `GEMINI_MODEL` to a model their account can use
> if they hit a "model not found / permission denied" error.

## Privacy / data flow
- Your chosen **topic and answers** are sent to Gemini to drive the session.
- `research_topic` performs **live web searches** and writes cited sources into
  your note.
- Lesson notes and your learner profile are written **locally** to the paths
  you configure; nothing is uploaded except what Gemini needs to respond.
- `learner_profile.json` (local study state) is git-ignored and never committed.

## Known limitations / before you publish
- **No automated tests or CI.** Behavior is verified manually. Add a smoke test
  before relying on this for others.
- **`skills/teach.prompt` is required.** If it is missing the tutor crashes on
  startup (`main.py` reads it directly). Ship it with the repo.
- **Obsidian is required for notes.** Without a valid `vault_path.txt` the
  session refuses to start. Non-Obsidian users must point `vault_path.txt` at
  any markdown file.
- **Diagram feature executes LLM-written code** (see Security Warning above).
- **Self-verification depends on a multimodal model.** If your `GEMINI_MODEL`
  can't review images, diagrams are marked "structural check only" — verify
  them yourself.

## License
GNU GPL v3 — see `LICENSE`.
