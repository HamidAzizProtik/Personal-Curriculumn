from extensions.md_log import log_to_obsidian


def record_source(title: str, passage: str, analysis: str = "") -> str:
    """Capture a primary-source passage (e.g. a quote from Machiavelli's
    *The Prince* or Marcus Aurelius' *Meditations*) together with your own
    analysis, formatted and appended to the Obsidian note.

    Use this when studying texts/books: paste the exact passage as
    `passage`, give the work as `title`, and write your interpretation or
    question in `analysis`. This keeps notes citable and structured.
    """
    block = f"> **{title}**\n> {passage.strip()}\n"
    if analysis and analysis.strip():
        block += f"\n**Analysis:** {analysis.strip()}\n"
    log_to_obsidian(block)
    return f"Logged source '{title}' to Obsidian."
