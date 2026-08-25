import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from google import genai
from google.genai import types
from google.genai.errors import APIError

from extensions.md_log import log_to_obsidian, get_obsidian_path
from extensions.quiz import ask_quiz
from agents.researcher import research_topic
from agents.mermaid_maker import generate_mermaid_dag
from agents.svg_maker import generate_svg_diagram


def run_tutor(topic: str):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[Error]: GEMINI_API_KEY environment variable is missing.")
        return

    # Set explicit 30s timeout to prevent socket hangs
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=30000)
    )

    prompt_path = os.path.join(CURRENT_DIR, "skills", "teach.prompt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_instruction = f.read()

    obsidian_path = get_obsidian_path()
    os.makedirs(os.path.dirname(obsidian_path), exist_ok=True)
    
    with open(obsidian_path, "a", encoding="utf-8") as f:
        f.write(f"\n\n# Learning Session: {topic}\n*Session initialized live via Gemini Tutor Harness*\n\n---\n")

    print(f"\n[Session Active]: Note File -> {obsidian_path}")

    tools = [
        log_to_obsidian,
        ask_quiz,
        research_topic,
        generate_mermaid_dag,
        generate_svg_diagram,
    ]

    chat = client.chats.create(
        model="gemini-3.6-flash",
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools,
            temperature=0.2,
        ),
    )

    try:
        response = chat.send_message(f"I want to learn: {topic}. Initiate the PROBE phase.")
    except APIError as e:
        print(f"\n[API Error]: {e.message}")
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

                try:
                    if fn_name == "log_to_obsidian":
                        res = log_to_obsidian(**fn_args)
                    elif fn_name == "ask_quiz":
                        res = ask_quiz(**fn_args)
                    elif fn_name == "research_topic":
                        res = research_topic(**fn_args)
                    elif fn_name == "generate_mermaid_dag":
                        dag = generate_mermaid_dag(**fn_args)
                        log_to_obsidian(f"```mermaid\n{dag}\n```")
                        res = "Mermaid DAG generated and logged to Obsidian."
                    elif fn_name == "generate_svg_diagram":
                        svg = generate_svg_diagram(**fn_args)
                        log_to_obsidian(f"```xml\n{svg}\n```")
                        res = "SVG diagram generated and logged to Obsidian."
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
                response = chat.send_message(function_responses)
            except Exception as e:
                print(f"\n[Network Stalled / Timeout]: {str(e)}")
                break
        else:
            if response.text:
                print(f"\n[Tutor]: {response.text}")
            
            user_input = input("\n[You]: ").strip()
            if user_input.lower() in ["exit", "quit"]:
                print("Session ended. All progress saved in Obsidian.")
                break
            
            try:
                response = chat.send_message(user_input)
            except Exception as e:
                print(f"\n[Network Stalled / Timeout]: {str(e)}")
                break


if __name__ == "__main__":
    target = input("Enter topic to learn: ").strip()
    if target:
        run_tutor(target)