"""Render external text without interpreting terminal control sequences."""


def safe_text(value: object) -> str:
    return "".join(char if char.isprintable() else f"\\u{ord(char):04x}" for char in str(value))
