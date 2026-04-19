"""
Lightweight AML entity extractor.

Pulls out candidate entities from a user query without a heavy NLP stack:
    - Capitalized multi-token names (party names / company names)
    - Quoted strings (explicit aliases)
    - Account-number-like patterns (>=8 digits, optionally hyphenated)
    - Known country/jurisdiction names from the config

For production you'd swap this for a proper NER model (e.g. spaCy,
Gemini-based extraction, or a finetuned model). The interface is stable.
"""
from __future__ import annotations

import re
from typing import Iterable

from agents.rag_agent.config.settings import get_settings

_CAP_PHRASE = re.compile(r"\b(?:[A-Z][a-zA-Z0-9&'.-]+)(?:\s+[A-Z][a-zA-Z0-9&'.-]+){0,5}\b")
_QUOTED = re.compile(r'"([^"]{2,})"|\'([^\']{2,})\'')
_ACCOUNT = re.compile(r"\b\d[\d\- ]{6,}\d\b")

_STOPWORDS = {
    "Who", "What", "Where", "When", "Why", "How", "Is", "Are", "Do", "Does",
    "The", "This", "That", "These", "Those", "A", "An", "And", "Or", "But",
    "I", "You", "We", "They",
}


class EntityExtractor:
    def __init__(self) -> None:
        self._jurisdictions = {
            j.lower() for j in get_settings().aml.high_risk_jurisdictions
        }

    def extract(self, text: str) -> list[str]:
        entities: set[str] = set()

        for match in _CAP_PHRASE.findall(text):
            cleaned = match.strip().strip(".,;:")
            # Skip things that are just a stopword (e.g. "Who").
            if cleaned in _STOPWORDS:
                continue
            entities.add(cleaned)

        for m in _QUOTED.finditer(text):
            quoted = (m.group(1) or m.group(2) or "").strip()
            if quoted:
                entities.add(quoted)

        for acc in _ACCOUNT.findall(text):
            entities.add(re.sub(r"[\s-]", "", acc))

        # Jurisdictions are case-insensitive matches from config.
        lower = text.lower()
        for j in self._jurisdictions:
            if j in lower:
                entities.add(j.title())

        return _dedup_preserve_order(entities)


def _dedup_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for i in items:
        key = i.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(i)
    return out
