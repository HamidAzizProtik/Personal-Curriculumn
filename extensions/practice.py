def practice_problem(problem: str, answer: str, hint: str = "") -> str:
    """Present a practice problem to the student and capture their answer.

    The tutor (model) authors the problem and knows the answer; this tool only
    presents it, reads the student's free-text answer, and returns both so the
    tutor can grade it, explain the method/shortcut, and log the result. This is
    the APPLICATION loop: applying material is what locks understanding in, so
    use it liberally — especially for skills like mental math. Do NOT reveal the
    answer to the student in your message; grade their response yourself.

    Args:
        problem: the problem statement to present (e.g. "47 x 12, mentally").
        answer: the correct answer (known to you, the tutor).
        hint: an optional hint to show the student before they answer.
    """
    print("\n==================== [ PRACTICE ] ====================")
    print(f"Solve (mentally if possible): {problem}")
    if hint:
        print(f"Hint: {hint}")
    print()
    try:
        student = input("Your answer: ").strip()
    except EOFError:
        student = ""
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
