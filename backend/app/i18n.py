"""Human messages only; API keys and enum values remain stable across languages."""

import json
from contextvars import ContextVar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "locales"
CATALOGS = {
    language: json.loads((ROOT / f"{language}.json").read_text()) for language in ("fr", "en")
}
language: ContextVar[str] = ContextVar("response_language", default="fr")


def select_language(header: str) -> str:
    choices = []
    for index, entry in enumerate(header.split(",")[:20]):
        parts = entry.strip().split(";")
        code = parts[0].strip().lower().split("-")[0]
        try:
            quality = float(
                next((p.strip()[2:] for p in parts[1:] if p.strip().startswith("q=")), "1")
            )
        except ValueError:
            continue
        if code in CATALOGS and 0 < quality <= 1:
            choices.append((quality, -index, code))
    return max(choices)[2] if choices else "fr"


def translate(message: str) -> str:
    catalog = CATALOGS[language.get()]
    return catalog.get(message, message)
