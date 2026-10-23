"""Best-effort masking shared by read-only adapters."""

import os
import re


def redact(text: str) -> str:
    # Best effort: do not claim to discover all application-specific secrets.
    token = os.environ.get("LOCALCOCKPIT_TOKEN")
    if token:
        text = text.replace(token, "[MASQUÉ]")
    text = re.sub(
        r"-----BEGIN [^-]*PRIVATE KEY-----.*?(?:-----END [^-]*PRIVATE KEY-----|$)",
        "[CLÉ PRIVÉE MASQUÉE]",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=\-]+", r"\1[MASQUÉ]", text)
    return re.sub(
        r"""(?ix)(["']?(?:password|passwd|token|api[_-]?key|secret)["']?\s*[:=]\s*)(?:"[^"\n]*"|'[^'\n]*'|[^\s,;]+)""",
        r"\1[MASQUÉ]",
        text,
    )
