# AI Tutor

A one-to-one AI tutor that runs a strict, pedagogically-grounded teaching loop:
it **probes** your prerequisites, **plans** a lesson DAG, then **teaches** one
node at a time with mandatory fact-checking, diagrams, and drills. It runs on
Gemini and persists a learner model across sessions so you start warm.

> ⚠️ **SECURITY WARNING — arbitrary code execution.**
> The diagram feature (`generate_diagram`) runs **LLM-generated Python
> (matplotlib) code on your machine**. Treat model output as untrusted. The
> harness strips secret environment variables before running this code, but a
> generated script can still read or modify local files. Only run the diagram
> agent on a machine you trust, and consider sandboxing it (limited user, no
> network, container) if you rely on it.

## Prerequisites
- Python 3.11+
- A Gemini API key (https://aistudio.google.com/apikey)

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

## Privacy / data flow
- Your chosen **topic and answers** are sent to Gemini to drive the session.
- `research_topic` performs **live web searches** and writes cited sources into
  your note.
- Lesson notes and your learner profile are written **locally** to the paths
  you configure; nothing is uploaded except what Gemini needs to respond.
- `learner_profile.json` (local study state) is git-ignored and never committed.

## License
GNU GPL v3 — see `LICENSE`.
