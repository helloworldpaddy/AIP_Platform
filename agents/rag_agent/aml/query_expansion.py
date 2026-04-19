"""
AML-aware query expansion.

Adds synonyms and risk-related vocabulary to a user query to improve
recall of both lexical (BM25) and dense retrieval. The expanded text is
never shown to the end user — it is only used as the retrieval query.
"""
from __future__ import annotations

from agents.rag_agent.config.settings import get_settings

# Domain-specific synonym clusters. These are intentionally conservative —
# over-expanding a query drowns vector retrieval in noise.
_SYNONYMS: dict[str, list[str]] = {
    "owner": ["beneficial owner", "UBO"],
    "beneficial owner": ["UBO", "ultimate beneficial owner"],
    "shell company": ["front company", "letterbox company"],
    "sanction": ["OFAC", "sanctions list", "SDN", "blocked person"],
    "sanctioned": ["OFAC", "SDN", "designated"],
    "pep": ["politically exposed person"],
    "laundering": ["money laundering", "placement", "layering", "integration"],
    "structuring": ["smurfing"],
    "wire": ["wire transfer", "SWIFT", "remittance"],
    "kyc": ["know your customer", "CDD", "EDD"],
    "str": ["suspicious transaction report", "SAR"],
    "sar": ["suspicious activity report", "STR"],
}


class QueryExpander:
    def __init__(self) -> None:
        self._settings = get_settings().aml

    def expand(self, query: str) -> str:
        if not query.strip() or not self._settings.enabled:
            return query

        low = query.lower()
        additions: list[str] = []

        for term, synonyms in _SYNONYMS.items():
            if term in low:
                for s in synonyms:
                    if s.lower() not in low and s not in additions:
                        additions.append(s)

        # Always include a small set of high-signal AML keywords when the
        # query looks like it's about risk (lightweight trigger).
        triggers = ("risk", "suspic", "launder", "sanction", "pep", "fraud")
        if any(t in low for t in triggers):
            for kw in self._settings.boost_keywords[:4]:
                if kw.lower() not in low and kw not in additions:
                    additions.append(kw)

        if not additions:
            return query
        return f"{query} " + " ".join(additions)
