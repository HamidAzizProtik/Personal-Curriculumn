import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from google import genai
from google.genai import types
from google.genai.errors import APIError

from config import MODEL, VERSION, get_client, menu
from extensions.md_log import log_to_obsidian, get_obsidian_path
from extensions.quiz import ask_quiz
from extensions.source import record_source
from extensions.phase_machine import PhaseMachine, Phase, build_phase_tools
from extensions.learner_model import LearnerModel, build_learner_tools
from extensions.practice import practice_problem, build_practice_tools
from agents.researcher import research_topic
from agents.mermaid_maker import generate_mermaid_dag
from agents.diagram_maker import generate_diagram
import time
import json
import hashlib

from throttle import pace, _is_rate_limit, _retry_after, BACKOFF_BASE, BACKOFF_FACTOR, MAX_RETRIES
from io_helpers import is_interactive, read_reply


def load_api_env():
    """Load credentials from a local env file if GEMINI_API_KEY is not set.

    Reads, in order: `api.env` then `.env` (first match wins). Supports both
    `KEY=VALUE` lines and a bare key on its own line. This lets the harness run
    from a plain terminal without manually exporting the variable first. Your
    key lives ONLY in this file (git-ignored); it is never hardcoded in code.
    No-op if the key is already present in the environment.
    """
    if os.environ.get("GEMINI_API_KEY"):
        return
    for fname in ("api.env", ".env"):
        api_env = os.path.join(CURRENT_DIR, fname)
        if not os.path.exists(api_env):
            continue
        with open(api_env, "r", encoding="utf-8-sig") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")
                elif not os.environ.get("GEMINI_API_KEY"):
                    os.environ["GEMINI_API_KEY"] = line
        if os.environ.get("GEMINI_API_KEY"):
            return


class _Streamed:
    """Lightweight accumulator for a streamed model response."""

    def __init__(self):
        self.text = ""
        self.function_calls: list = []


def _stream_chat(chat, message, prefix="[Tutor]: ") -> _Streamed:
    """Send a message with response streaming.

    Prints the tutor's text tokens live (so the session feels responsive
    instead of hanging on a blank line) and returns a lightweight object
    exposing `.text` (full joined text) and `.function_calls` (list).

    Resilient to free-tier rate limits: a 429/5xx triggers an exponential
    backoff and retry rather than ending the session.
    """
    out = _Streamed()
    printed_prefix = False
    delay = BACKOFF_BASE
    for attempt in range(MAX_RETRIES + 1):
        try:
            pace()
            # google-genai 2.x exposes streaming as a dedicated method.
            for chunk in chat.send_message_stream(message):
                if getattr(chunk, "text", None):
                    if not printed_prefix and prefix:
                        print("\n" + prefix, end="", flush=True)
                        printed_prefix = True
                    print(chunk.text, end="", flush=True)
                    out.text += chunk.text
                fcs = getattr(chunk, "function_calls", None)
                if fcs:
                    out.function_calls.extend(fcs)
            if printed_prefix:
                print()
            return out
        except Exception as e:
            if attempt >= MAX_RETRIES or not _is_rate_limit(e):
                raise
            ra = _retry_after(e)
            sleep_for = ra if ra else delay
            print(f"\n[Rate limit] backing off {sleep_for:.0f}s "
                  f"(attempt {attempt + 1}/{MAX_RETRIES})", flush=True)
            time.sleep(sleep_for)
            delay *= BACKOFF_FACTOR
            # Reset so a retry restarts cleanly (no partial prefix left dangling).
            out = _Streamed()
            printed_prefix = False


def _try_cached_system(client, model, system_instruction):
    """Best-effort Gemini context caching of the (large, static) system prompt.

    Cuts per-call token cost on the free tier and is faster. Silently falls back
    to a plain system_instruction when the model/SDK doesn't support caching or
    the prompt is below the caching minimum.
    """
    try:
        from google.genai import types as _t
        pace()
        cached = client.caches.create(
            model=model,
            config=_t.CreateCachedContentConfig(
                display_name="tutor-system",
                ttl="7200s",
            ),
            contents=[system_instruction],
        )
        return cached.name
    except Exception:
        return None


def _session_ckpt_path(topic: str):
    h = hashlib.sha256(topic.encode("utf-8")).hexdigest()[:16]
    return os.path.join(CURRENT_DIR, ".cache", f"session_{h}.json")


def _save_checkpoint(topic, chat, pm):
    """Persist live conversation + phase state so a killed session can resume.

    Best-effort: any serialization failure is swallowed so the live session is
    never affected. Falls back to a fresh session on the next resume attempt.
    """
    try:
        path = _session_ckpt_path(topic)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        history = [c.model_dump() for c in chat.get_history()]
        if not history:
            return
        state = {
            "topic": topic,
            "model": MODEL,
            "ts": time.time(),
            "history": history,
            "pm": {
                "phase": pm.phase.value,
                "probe_quiz_count": pm.probe_quiz_count,
                "probe_strands": list(pm.probe_strands),
                "dag_generated": pm.dag_generated,
                "plan_researched": pm.plan_researched,
                "node_index": pm.node_index,
                "node_passed": pm.node_passed,
                "node_researched": pm.node_researched,
                "probe_strand_counts": pm.probe_strand_counts,
                "probe_budget_exhausted": pm.probe_budget_exhausted,
            },
        }
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except Exception:
        pass


def _load_checkpoint(topic):
    try:
        path = _session_ckpt_path(topic)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _clear_checkpoint(topic):
    try:
        path = _session_ckpt_path(topic)
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _restore_pm(pm, st):
    pm.phase = Phase[st["phase"]]
    pm.probe_quiz_count = st["probe_quiz_count"]
    pm.probe_strands = set(st.get("probe_strands", []))
    pm.dag_generated = st["dag_generated"]
    pm.plan_researched = st["plan_researched"]
    pm.node_index = st["node_index"]
    pm.node_passed = st["node_passed"]
    pm.node_researched = st["node_researched"]
    pm.probe_strand_counts = st.get("probe_strand_counts", {})
    pm.probe_budget_exhausted = st["probe_budget_exhausted"]


def run_tutor(topic: str, resume: bool = False):
    load_api_env()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[Error]: GEMINI_API_KEY environment variable is missing. "
              "Set it, or add it to api.env / .env (see README).")
        return

    # Reuse the shared, pooled client (same generous 120s timeout) so sub-agent
    # calls and the tutor share one connection pool instead of two.
    client = get_client()

    prompt_path = os.path.join(CURRENT_DIR, "skills", "teach.prompt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_instruction = f.read()

    # Persistent, cross-session learner model: loaded (warm) and injected into
    # the system prompt so the tutor does not start cold each run.
    learner = LearnerModel.load(topic)
    learner.record_session_start()
    system_instruction = (
        system_instruction + "\n\n" + learner.context_prompt()
    )

    # Hard PROBE -> PLAN -> TEACH state machine. The harness enforces phase
    # ordering; forward tools are blocked until the matching gate passes.
    pm = PhaseMachine()
    phase_gate_tools = build_phase_tools(pm, learner)
    learner_tools = build_learner_tools(learner)
    practice_tools = build_practice_tools()
    complete_probe, complete_plan, complete_node = phase_gate_tools
    probe_prerequisite, record_calibration = learner_tools

    try:
        obsidian_path = get_obsidian_path()
    except FileNotFoundError as e:
        print(f"\n[Setup needed]: {e}")
        return
    os.makedirs(os.path.dirname(obsidian_path), exist_ok=True)

    with open(obsidian_path, "a", encoding="utf-8") as f:
        f.write(f"\n\n# Learning Session: {topic}\n*Session initialized live via Gemini Tutor Harness*\n\n---\n")

    print(f"\n[Session Active]: Note File -> {obsidian_path}")
    print(f"[AI Tutor v{VERSION}] PROBE -> PLAN -> TEACH. Be precise; the harness enforces each gate.")
    print(f"[Model]: {MODEL}")

    tools = [
        log_to_obsidian,
        ask_quiz,
        research_topic,
        record_source,
        generate_mermaid_dag,
        generate_diagram,
        practice_problem,
        *phase_gate_tools,
        *learner_tools,
    ]

    # Best-effort system-prompt caching (free-tier token savings); falls back
    # silently when unsupported. A single shared cached content is reused for
    # every turn of this session.
    cache_name = _try_cached_system(client, MODEL, system_instruction)

    def _make_chat(history=None):
        cfg = {"tools": tools, "temperature": 0.2}
        if cache_name:
            cfg["cached_content"] = cache_name
        else:
            cfg["system_instruction"] = system_instruction
        kw = {"model": MODEL, "config": types.GenerateContentConfig(**cfg)}
        if history is not None:
            kw["history"] = history
        return client.chats.create(**kw)

    # Resume a previous (throttled/killed) session if requested and a checkpoint
    # exists, rebuilding both the conversation and the phase machine.
    ckpt = _load_checkpoint(topic) if resume else None
    resumed = False
    if ckpt and ckpt.get("history"):
        try:
            history = [types.Content.model_validate(d) for d in ckpt["history"]]
            _restore_pm(pm, ckpt["pm"])
            chat = _make_chat(history)
            resumed = True
        except Exception:
            chat = _make_chat()
    else:
        chat = _make_chat()

    # Prime the conversation.
    response: _Streamed
    try:
        if resumed:
            print("[Resumed] Restoring previous session state.")
            response = _stream_chat(
                chat,
                "Continuing our session. Resume the lesson from exactly where we "
                "left off, honoring the current phase and all gates.",
            )
        else:
            response = _stream_chat(
                chat, f"I want to learn: {topic}. Initiate the PROBE phase."
            )
    except APIError as e:
        print(f"\n[API Error]: {getattr(e, 'message', str(e))}")
        return
    except Exception as e:
        print(f"\n[API Error]: {str(e)}")
        return

    while True:
        if response.function_calls:
            function_responses = []
            for call in response.function_calls:
                fn_name = call.name
                if not fn_name:
                    continue
                
                fn_args = call.args or {}
                print(f"[Tool Execution]: {fn_name}")

                # Hard phase enforcement: block any tool that violates the
                # current phase contract before it can run. This is what makes
                # PROBE -> PLAN -> TEACH a real state machine rather than a
                # prompt suggestion.
                allowed, block_msg = pm.can_execute(fn_name, fn_args)
                if not allowed:
                    res = block_msg
                else:
                    try:
                        if fn_name == "log_to_obsidian":
                            res = log_to_obsidian(**fn_args)
                        elif fn_name == "probe_prerequisite":
                            res = probe_prerequisite(**fn_args)
                            pm.mark_probe_call(fn_args.get("prerequisite", ""))
                        elif fn_name == "ask_quiz":
                            res = ask_quiz(**fn_args)
                            correct = "Incorrect" not in res
                            pm.record_quiz_outcome(correct)
                            learner.record_quiz(fn_args.get("question", ""), correct)
                        elif fn_name == "research_topic":
                            res = research_topic(**fn_args)
                            pm.mark_researched()
                        elif fn_name == "record_source":
                            res = record_source(**fn_args)
                        elif fn_name == "practice_problem":
                            res = practice_problem(**fn_args)
                        elif fn_name == "generate_mermaid_dag":
                            dag = generate_mermaid_dag(**fn_args)
                            if "Error" in dag or "No DAG generated" in dag:
                                res = (
                                    f"Mermaid DAG generation failed: {dag}. "
                                    "Fix and retry before calling complete_plan."
                                )
                            else:
                                log_to_obsidian(f"```mermaid\n{dag}\n```")
                                pm.mark_dag_generated()
                                learner.record_plan(dag)
                                res = "Mermaid DAG generated and logged to Obsidian."
                        elif fn_name == "generate_diagram":
                            diag = generate_diagram(**fn_args)
                            log_to_obsidian(diag)
                            res = f"Diagram generated and embedded: {diag}" if diag.startswith("![[") else diag
                        elif fn_name == "complete_probe":
                            res = complete_probe()
                        elif fn_name == "complete_plan":
                            res = complete_plan()
                        elif fn_name == "complete_node":
                            res = complete_node()
                        elif fn_name == "record_calibration":
                            res = record_calibration(**fn_args)
                        else:
                            res = f"Tool '{fn_name}' not found."
                    except Exception as err:
                        res = f"Execution error in tool {fn_name}: {str(err)}"

                function_responses.append(
                    types.Part.from_function_response(
                        name=fn_name,
                        response={"result": res}
                    )
                )

            try:
                response = _stream_chat(chat, function_responses)
            except Exception as e:
                print(f"\n[Network Stalled / Timeout]: {str(e)}")
                break
            _save_checkpoint(topic, chat, pm)
        else:
            user_input = read_reply("\n[You]: ")
            if user_input is None:
                # Headless / closed stdin: stop cleanly instead of crashing.
                print("\n[Session ended]: input stream closed. Saving progress.")
                _clear_checkpoint(topic)
                break
            user_input = user_input.strip()
            if user_input.lower() in ["exit", "quit"]:
                print("Session ended. All progress saved in Obsidian.")
                _clear_checkpoint(topic)
                break

            try:
                response = _stream_chat(chat, user_input)
            except Exception as e:
                print(f"\n[Network Stalled / Timeout]: {str(e)}")
                break
            _save_checkpoint(topic, chat, pm)

    # Persist the learner model so the next session starts warm.
    learner.save()
    print("[Learner model saved for future sessions.]")


if __name__ == "__main__":
    menu()
    # Topic priority: CLI argument -> TUTOR_TOPIC env -> interactive prompt.
    # `--resume` rebuilds a previously throttled/killed session for the topic.
    args = sys.argv[1:]
    resume = False
    if args and args[0] == "--resume":
        resume = True
        args = args[1:]
    if args:
        target = " ".join(args).strip()
    elif os.environ.get("TUTOR_TOPIC"):
        target = os.environ["TUTOR_TOPIC"].strip()
    else:
        target = (read_reply("Enter topic to learn: ") or "").strip()

    if not target:
        if is_interactive():
            print("[Error]: No topic provided. Pass it as an argument "
                  "(main.py \"mental math\") or type one when prompted.")
        else:
            print("[Error]: No topic provided and no terminal to prompt. "
                  "Pass it as an argument, set TUTOR_TOPIC, or pipe a topic "
                  "via TUTOR_REPLIES.")
        sys.exit(1)

    if target:
        try:
            run_tutor(target, resume=resume)
        except KeyboardInterrupt:
            print("\n[Session ended by user.]")
        except Exception as e:
            print(f"\n[Fatal error]: {e}")