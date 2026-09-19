"""Conservative token estimation and hard caps, with no tokenizer dependency.

Deliberately pessimistic, because these numbers bound spend: ASCII is counted
at 1 token per 3 characters (real English is closer to 4), and every non-ASCII
character is counted as a full token, since CJK text tokenizes at roughly one
token per character. A character cap alone would let a Chinese README cost
four times what an English one does.
"""

from __future__ import annotations

ASCII_CHARS_PER_TOKEN = 3


def _cost(ch: str) -> float:
    return 1 / ASCII_CHARS_PER_TOKEN if ord(ch) < 128 else 1.0


def estimate_tokens(text: str) -> int:
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    other = len(text) - ascii_chars
    return -(-ascii_chars // ASCII_CHARS_PER_TOKEN) + other  # ceil division


def cap_tokens(text: str, max_tokens: int) -> str:
    """Longest prefix of `text` within `max_tokens`, cut at a line break if one
    falls in the last quarter of the allowed window."""
    if estimate_tokens(text) <= max_tokens:
        return text
    spent, cut = 0.0, 0
    for i, ch in enumerate(text):
        spent += _cost(ch)
        if spent > max_tokens - 1:  # headroom for the ceil in estimate_tokens
            break
        cut = i + 1
    window = text[:cut]
    boundary = window.rfind("\n")
    if boundary > cut * 3 // 4:
        window = window[:boundary]
    return window.rstrip()
