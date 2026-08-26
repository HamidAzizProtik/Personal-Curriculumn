from extensions.md_log import log_to_obsidian


def record_source(title: str, passage: str, analysis: str = "") -> str:
    """Log a primary-source `passage` (with `title` and optional `analysis`) to Obsidian, formatted and citable."""
    block = f"> **{title}**\n> {passage.strip()}\n"
    if analysis and analysis.strip():
        block += f"\n**Analysis:** {analysis.strip()}\n"
    log_to_obsidian(block)
    return f"Logged source '{title}' to Obsidian."
