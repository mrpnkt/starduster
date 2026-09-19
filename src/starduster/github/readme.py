"""README preparation: strip what costs tokens but says nothing, then cap.

Typical README heads are badge walls, centred logo HTML, screenshots, and
occasionally multi-kilobyte base64 images. Removing those first means the
token budget is spent on the prose that actually says what a project is.
"""

from __future__ import annotations

import re

from ..config import README_MAX_TOKENS
from ..tokens import cap_tokens

# Credentials that turn up in third-party READMEs (often in security tooling
# docs, sometimes real). Redacted before anything is stored: GitHub push
# protection would block the daily data commit, and republishing someone's
# leaked key is wrong regardless.
_SECRETS = tuple(re.compile(p, re.DOTALL) for p in (
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    r"https://hooks\.slack\.com/services/[A-Za-z0-9_/]+",
    r"https://(?:discord|discordapp)\.com/api/webhooks/\d+/[A-Za-z0-9_-]+",
    r"xox[abposr]-[A-Za-z0-9-]{10,}",
    r"\bgh[pousr]_[A-Za-z0-9]{36,}",
    r"\bgithub_pat_[A-Za-z0-9_]{22,}",
    r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    r"\bAIza[0-9A-Za-z_-]{35}\b",
    r"\bsk-ant-[A-Za-z0-9_-]{20,}",
    r"\bsk-[A-Za-z0-9]{40,}",
))
REDACTED = "[redacted]"


def redact_secrets(text: str) -> str:
    for pattern in _SECRETS:
        text = pattern.sub(REDACTED, text)
    return text


_COMMENTS = re.compile(r"<!--.*?-->", re.DOTALL)
_DATA_URIS = re.compile(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=\s]*")
_IMAGES = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_EMPTY_LINKS = re.compile(r"\[\s*\]\([^)]*\)")
_LINKS = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_TAGS = re.compile(r"<[^>\n]+>")
_TRAILING_SPACE = re.compile(r"[ \t]+\n")
_BLANK_RUNS = re.compile(r"\n{3,}")


def clean_readme(text: str) -> str:
    out = _COMMENTS.sub("", redact_secrets(text))
    out = _DATA_URIS.sub("", out)
    out = _IMAGES.sub("", out)        # badges become `[](link)` ...
    out = _EMPTY_LINKS.sub("", out)   # ... which is removed here
    out = _LINKS.sub(r"\1", out)
    out = _TAGS.sub("", out)
    out = _TRAILING_SPACE.sub("\n", out)
    out = "\n".join(line for line in out.split("\n") if line.strip() or not line)
    out = _BLANK_RUNS.sub("\n\n", out)
    return out.strip()


def prepare_readme(text: str, max_tokens: int = README_MAX_TOKENS) -> str:
    return cap_tokens(clean_readme(text), max_tokens)
