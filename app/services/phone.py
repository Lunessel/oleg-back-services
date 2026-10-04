import re

_PHONE_RE = re.compile(r"^(\+380|0)\d{9}$")


def normalize_phone(raw: str) -> str | None:
    """Return the number as +380XXXXXXXXX / 0XXXXXXXXX, or None if it is not a valid UA number."""
    cleaned = re.sub(r"[^\d+]", "", raw)
    if cleaned.startswith("380"):
        cleaned = "+" + cleaned
    return cleaned if _PHONE_RE.match(cleaned) else None
