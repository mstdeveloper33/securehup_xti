"""Render external text without interpreting terminal control sequences."""

import shlex


def xti_command(*arguments: str, data_dir=None) -> str:
    """Printable navigation only, with the selected workspace retained."""
    prefix = ("./xti", "--data-dir", str(data_dir)) if data_dir is not None else ("./xti",)
    return safe_text(shlex.join((*prefix, *arguments)))


def safe_text(value: object) -> str:
    return "".join(char if char.isprintable() else f"\\u{ord(char):04x}" for char in str(value))
