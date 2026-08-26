from extensions.md_log import log_to_obsidian
from io_helpers import read_reply

def ask_quiz(question: str, options: list[str], correct_idx: int, explanation: str) -> str:
    """Run a multiple-choice quiz: present `options`, read the student's choice, log the result, and return Correct/Incorrect with the explanation."""
    print(f"\n==================== [ QUIZ PROBE ] ====================")
    print(f"Question: {question}\n")
    for i, opt in enumerate(options):
        print(f"  [{i + 1}] {opt}")
    
    user_choice = -1
    while True:
        raw = read_reply("\nYour Answer (enter option number): ")
        if raw is None:
            # Headless / no terminal: can't collect an answer, skip grading.
            print("[headless] No answer supplied; skipping quiz grading.")
            break
        raw_input = raw.strip()
        try:
            choice = int(raw_input) - 1
            if 0 <= choice < len(options):
                user_choice = choice
                break
            print(f"Invalid range. Please enter a number between 1 and {len(options)}.")
        except ValueError:
            print("Invalid input. Enter an integer choice.")

    is_correct = (user_choice == correct_idx)
    result_msg = "✓ CORRECT!" if is_correct else f"✗ INCORRECT. Correct answer was [{correct_idx + 1}] {options[correct_idx]}"
    
    print(f"\n-> {result_msg}")
    print(f"Explanation: {explanation}")
    print(f"========================================================\n")

    quiz_md = f"> **Quiz**: {question}\n> - **User Answer**: [{user_choice + 1}] {options[user_choice]}\n> - **Result**: {'✓ Correct' if is_correct else '✗ Incorrect'}\n> - **Explanation**: {explanation}"
    log_to_obsidian(quiz_md)

    return f"User answered: {'Correct' if is_correct else 'Incorrect'}. User choice: {user_choice + 1}."