from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


class DemoKycProvider:
    """A deterministic demo KYC provider (no external dependencies)."""

    async def lookup(self, party_id: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        base = {
            "party_id": party_id,
            "name": party_id,
            "dob": None,
            "nationality": None,
            "country_of_residence": None,
            "occupation": None,
            "pep": False,
            "sanctions_clear": True,
            "risk_rating": "MEDIUM",
            "kyc_refreshed_at": (now - timedelta(days=90)).isoformat(),
        }

        # Tiny bit of flavor for the seeded demo entities.
        if party_id == "P-DEMO-SUBJECT":
            return {
                **base,
                "name": "Demo Subject Ltd.",
                "country_of_residence": "US",
                "risk_rating": "HIGH",
            }
        if party_id == "P-CP-GB-003":
            return {
                **base,
                "name": "Thames Consulting LLP",
                "country_of_residence": "GB",
                "pep": True,
                "risk_rating": "HIGH",
            }
        if party_id in {"P-CP-PA-001", "P-INT-001"}:
            return {
                **base,
                "name": party_id,
                "country_of_residence": "PA" if party_id == "P-CP-PA-001" else "VG",
                "risk_rating": "HIGH",
            }
        return base


class DemoSearchProvider:
    """A deterministic demo web-search provider (returns canned results)."""

    async def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        q = query.lower()
        results: list[dict[str, Any]] = []
        if "sanction" in q or "ofac" in q:
            results.append(
                {
                    "title": "OFAC SDN list – no direct match (demo)",
                    "url": "https://ofac.treasury.gov/",
                    "snippet": "Demo provider: no sanctions matches found for the queried entity.",
                    "source": "ofac.treasury.gov",
                    "category": "SANCTIONS",
                    "severity": "low",
                    "published_at": None,
                }
            )
        if "adverse" in q or "fraud" in q or "shell" in q:
            results.append(
                {
                    "title": "Adverse media check – inconclusive (demo)",
                    "url": "https://example.com/demo-adverse-media",
                    "snippet": "Demo provider: no reliable adverse media found in sample sources.",
                    "source": "example.com",
                    "category": "ADVERSE_MEDIA",
                    "severity": "low",
                    "published_at": None,
                }
            )
        return results[: max(1, int(max_results))]

