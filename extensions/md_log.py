import os

def get_obsidian_path() -> str:
    """Reads target note location from vault_path.txt, stripping BOMs, quotes, and whitespace."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path_file = os.path.join(base_dir, "vault_path.txt")
    if not os.path.exists(path_file):
        raise FileNotFoundError(f"vault_path.txt not found at {path_file}")
    
    with open(path_file, "r", encoding="utf-8-sig") as f:
        raw_path = f.read().strip().strip('"').strip("'")
    return raw_path

def log_to_obsidian(content: str) -> str:
    """Appends formatted Markdown content directly into the active Obsidian lesson file."""
    path = get_obsidian_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n\n" + content.strip() + "\n")
    return f"Logged content to Obsidian note at: {path}"