import re

def slugify(text: str) -> str:
    """Create a filesystem-safe slug from a title."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")
