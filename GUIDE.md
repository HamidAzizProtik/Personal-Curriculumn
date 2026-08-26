# AI Tutor — User Guide (v1.0.0)

A one-to-one AI tutor that implements the learning philosophy from the
"How to use AI to learn better" design: **optimized teaching** (the lesson is
fitted to *your* exact edge of understanding) and **optimized allocation of
mental resources** (the system absorbs planning, sourcing, verifying, and
diagramming so all your struggle goes into the material itself).

> The harness does not trust the model on vibes. It enforces a hard
> PROBE → PLAN → TEACH state machine, mandatory fact‑checking, self‑verified
> diagrams, and a persistent learner model that survives across sessions.

---

## 1. What the tutor does

| Phase | What happens | Hard gate |
|-------|-------------|-----------|
| **PROBE** | Binary‑searches your understanding across prerequisite *strands* with graded MCQs (`probe_prerequisite`). | Needs ≥4 distinct strands & ≥6 quizzes before `complete_probe` unlocks PLAN. |
| **PLAN** | Builds a Mermaid DAG of the lesson (forces the model to reason everything out) and fact‑checks it (`research_topic`). | `complete_plan` is blocked until `research_topic` ran this phase. |
| **TEACH** | Walks the DAG **one node at a time**. Explain → (optional diagram) → fact‑check → **drill with `practice_problem`** → verify with `ask_quiz` → `complete_node()`. | After a node quiz *passes*, new material is blocked until `complete_node()`; each node also requires a `research_topic` verification. |

Continuous verification is mandatory: every plan and every teaching node must
be fact‑checked before it can be closed. Diagrams are rendered by matplotlib
and then **self‑verified** (valid PNG + vision review); if the check fails it
retries with the reviewer's feedback and, failing that, flags the image.

---

## 2. Setup (one time)

Requirements: Python 3.11+, a Gemini API key.

```bash
pip install google-generativeai matplotlib numpy
```

1. **API key** — create `api.env` in the project root:
   ```
   GEMINI_API_KEY=your_key_here
   ```
   Optional: `GEMINI_MODEL=gemini-3.6-flash` (this is the default and the only
   model supported for new users; older 2.5 models are remapped automatically).
2. **Note file** — put the absolute path to your Obsidian note in `vault_path.txt`:
   ```
   D:\Personal-Curriculumn\personal-curriculumn\learning\lesson.md
   ```
   The diagram attachment folder is auto‑detected from your vault's
   `.obsidian/app.json` (defaults to `Attachments`).

Run it:
```bash
python main.py
```
Enter a topic when prompted. Everything is streamed to the terminal **and**
appended to your Obsidian note.

---

## 3. Your side of the contract

The harness blocks the model when it breaks the rules; you only have to:

- **Answer probe quizzes** honestly — this is what builds your calibrated map.
  Don't guess; say "I don't know" when you don't.
- **Do the practice problems.** When `practice_problem` prints a problem, type
  your answer. The tutor grades it and explains the *technique*, not just the
  result. This application step is what locks learning in.
- **Type naturally** between turns: ask for a different explanation, request
  more drills, or ask it to re‑quiz earlier nodes (spaced recall).

If the model ever tries to skip a phase or rush ahead, you'll see a `BLOCKED`
message — that's the guard working; the model must comply.

---

## 4. Learning mental math (the main use case)

Mental math is *application*, not watching. The tool is built for exactly this
because of the `practice_problem` drill loop.

### 4.1 Start the session
```
Enter topic to learn: Mental math: fast addition, subtraction,
multiplication, and division in my head (2–4 digit numbers, using shortcuts)
```

### 4.2 What PROBE will do
It will probe each strand to your failure boundary, e.g.:
- Addition: left‑to‑right, compensation (round→fix), grouping.
- Subtraction: borrow vs. equal‑additions method, subtracting from round numbers.
- Multiplication: distributive splitting, behind‑10s/11s/5s tricks, doubling/halving, difference of squares.
- Division: chunking, short division, multiplying by reciprocals.

Answer truthfully. The deeper you let it probe (it asks easy→medium→hard on
each strand), the more exact your syllabus becomes.

### 4.3 Steer TEACH toward drilling
The single highest‑leverage instruction you can give (say it once at the start
of TEACH, or put it in your topic line):

> "For every node, drill me with 3 `practice_problem` mental‑math questions and
> then teach me the shortcut/trick I should have used. Also quiz me on earlier
> nodes every few steps (spaced recall)."

The tutor will then, per node: explain the trick → give you problems to solve
mentally → grade you → show the fast method → verify with `ask_quiz` →
`complete_node()`.

### 4.4 Example prompts you can paste
- "Give me a harder variant and time‑pressure me." (still type your answer)
- "Show the visual/number‑line diagram for this shortcut." (triggers `generate_diagram`)
- "I got that wrong — re‑teach and give me 2 more drills."
- "Quiz me again on the subtraction tricks from 3 nodes ago." (spaced recall)
- "Log the trick sheet to Obsidian." (it will `log_to_obsidian` a summary)

### 4.5 What "good" looks like
You should feel *struggle* — that's the point. If it's too easy, tell it to
raise difficulty; the persistent learner model will remember your gaps next
session and start there.

---

## 5. Performance notes (v1.0.0 optimizations)

These changes make the tool faster **without touching quality**:
- **One shared client** — all sub‑agents reuse a single cached `genai.Client`
  (60s timeout) instead of reconstructing one per tool call.
- **Deterministic sub‑agent generation** — code‑gen (diagrams, DAG) and
  research run at `temperature=0.2`, so they're concise and reliable (less
  token waste = faster, fewer bad outputs).
- **Research cache** — identical in‑session research queries return the cached,
  already‑verified result instead of re‑hitting the API.

No teaching behavior, verification, or gating was removed or weakened.

---

## 6. Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `GEMINI_API_KEY environment variable is missing` | Add it to `api.env`. |
| Diagram returns "matplotlib is not installed" | `pip install matplotlib numpy`. The harness degrades gracefully (no crash). |
| Diagram note says "self‑verification could NOT be fully run" | The model isn't multimodal; only structural checks passed. Confirm visually. |
| PROBE won't end ("BLOCKED: ... minimum ...") | Probe more strands / more quizzes — that's the depth gate working. |
| `RecordedSources` / no citations | Grounding unavailable for the model; the note says so honestly. |

---

## 7. Personal‑use tips

- **Keep `vault_path.txt` stable.** Your `learner_profile.json` (one file,
  keyed by topic) accumulates probe results and quiz history, so each new
  session starts *warm* — it skips what you've proven you know and prioritizes
  your gaps.
- **Calibrate honestly.** The model can only map your real edge if you answer
  probes truthfully. Gaslighting yourself just poisons next session's start.
- **Use it as a drill partner, not a lecture.** Mental math, languages, and
  proofs all improve most from the `practice_problem` loop — lean on it.

---

## 8. Release status

- Version: **1.0.0** (printed at session start).
- Enforced: phase state machine, per‑node gating, mandatory per‑node &
  per‑plan verification, diagram self‑verification, persistent learner model.
- Stable for daily personal use. The only soft spots are inherent to LLM
  control: probe *depth* is encouraged (not content‑graded) and a
  `research_topic` call is required but its output must be logged by the model
  (prompt‑enforced). Both are mitigating via the instructions in `teach.prompt`.
