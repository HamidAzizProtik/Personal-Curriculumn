from extensions.md_log import log_to_obsidian

def ask_quiz(question: str, options: list[str], correct_idx: int, explanation: str) -> str:
    """Presents an interactive multiple-choice terminal quiz and logs results to Obsidian."""
    print(f"\n==================== [ QUIZ PROBE ] ====================")
    print(f"Question: {question}\n")
    for i, opt in enumerate(options):
        print(f"  [{i + 1}] {opt}")
    
    user_choice = -1
    while True:
        try:
            raw_input = input("\nYour Answer (enter option number): ").strip()
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