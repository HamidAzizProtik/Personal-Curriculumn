from io_helpers import read_reply


def practice_problem(problem: str, answer: str, hint: str = "") -> str:
    """Present a `problem` (with optional `hint`), read the student's free-text answer, and return both so you can grade it and log the result. Do NOT reveal `answer`."""
    print("\n==================== [ PRACTICE ] ====================")
    print(f"Solve (mentally if possible): {problem}")
    if hint:
        print(f"Hint: {hint}")
    print()
    student = (read_reply("Your answer: ") or "").strip()
    print("=====================================================\n")

    return (
        f"Practice problem presented: {problem}\n"
        f"Student answer: {student}\n"
        f"Tutor's known answer: {answer}\n"
        "Now grade the student's answer, explain the correct technique/shortcut "
        "(especially mental-math tricks), and log a concise note to Obsidian if "
        "it is worth revisiting."
    )


def build_practice_tools():
    """Expose the practice tool to the model."""
    return [practice_problem]
