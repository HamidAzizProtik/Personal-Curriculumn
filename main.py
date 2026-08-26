import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from google import genai
from google.genai import types
from google.genai.errors import APIError

from config import MODEL, VERSION, get_client
from extensions.md_log import log_to_obsidian, get_obsidian_path
from extensions.quiz import ask_quiz
from extensions.source import record_source
from extensions.phase_machine import PhaseMachine, build_phase_tools
from extensions.learner_model import LearnerModel, build_learner_tools
from extensions.practice import practice_problem, build_practice_tools
from agents.researcher import research_topic
from agents.mermaid_maker import generate_mermaid_dag
from agents.diagram_maker import generate_diagram
from io_helpers import is_interactive, read_reply


def load_api_env():
    """Load credentials from api.env if GEMINI_API_KEY is not already set.

    Supports both `KEY=VALUE` lines and a bare key on its own line.
    This lets the harness run from a plain terminal without manually
    exporting the variable first. No-op if the key is already present.
    """
    if os.environ.get("GEMINI_API_KEY"):
        return
    api_env = os.path.join(CURRENT_DIR, "api.env")
    if not os.path.exists(api_env):
        return
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


def _stream_chat(chat, message, prefix="[Tutor]: "):
    """Send a message with response streaming.

    Prints the tutor's text tokens live (so the session feels responsive
    instead of hanging on a blank line) and returns a lightweight object
    exposing `.text` (full joined text) and `.function_calls` (list) — exactly
    what the main loop already consumes.
    """
    class _Streamed:
        def __init__(self):
            self.text = ""
            self.function_calls = []

    out = _Streamed()
    printed_prefix = False
    # google-genai 2.x exposes streaming as a dedicated method (not a kwarg).
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


def run_tutor(topic: str):
    load_api_env()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[Error]: GEMINI_API_KEY environment variable is missing. "
              "Set it or add it to api.env.")
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

    obsidian_path = get_obsidian_path()
    os.makedirs(os.path.dirname(obsidian_path), exist_ok=True)
    
    with open(obsidian_path, "a", encoding="utf-8") as f:
        f.write(f"\n\n# Learning Session: {topic}\n*Session initialized live via Gemini Tutor Harness*\n\n---\n")

    print(f"\n[Session Active]: Note File -> {obsidian_path}")
    print(f"[AI Tutor v{VERSION}] PROBE -> PLAN -> TEACH. Be precise; the harness enforces each gate.")

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

    chat = client.chats.create(
        model=MODEL,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools,
            temperature=0.2,
        ),
    )

    try:
        response = _stream_chat(chat, f"I want to learn: {topic}. Initiate the PROBE phase.")
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
        else:
            user_input = read_reply("\n[You]: ")
            if user_input is None:
                # Headless / closed stdin: stop cleanly instead of crashing.
                print("\n[Session ended]: input stream closed. Saving progress.")
                break
            user_input = user_input.strip()
            if user_input.lower() in ["exit", "quit"]:
                print("Session ended. All progress saved in Obsidian.")
                break

            try:
                response = _stream_chat(chat, user_input)
            except Exception as e:
                print(f"\n[Network Stalled / Timeout]: {str(e)}")
                break

    # Persist the learner model so the next session starts warm.
    learner.save()
    print("[Learner model saved for future sessions.]")


if __name__ == "__main__":
    # Topic priority: CLI argument -> TUTOR_TOPIC env -> interactive prompt.
    # This lets a headless launch supply a topic without a terminal.
    if len(sys.argv) > 1:
        target = " ".join(sys.argv[1:]).strip()
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
            run_tutor(target)
        except KeyboardInterrupt:
            print("\n[Session ended by user.]")
        except Exception as e:
            print(f"\n[Fatal error]: {e}")