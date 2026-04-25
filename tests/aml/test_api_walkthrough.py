"""End-to-end FastAPI walkthrough.

Same flow as `test_orchestrator_walkthrough.py`, but driven through the
HTTP layer using `httpx.AsyncClient` + `ASGITransport`.  The dependency
overrides in `conftest.py` swap the production agent registry for the
deterministic stubs, so this test is hermetic w.r.t. external services.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.integration

_HEADERS = {"X-Analyst-Id": "analyst.test"}


def _client(app) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(
        transport=transport, base_url="http://aml-test", headers=_HEADERS
    )


async def test_full_walkthrough_via_api(api_app, case_number: str) -> None:
    async with _client(api_app) as client:
        # ---- 1. Create the case --------------------------------------------
        r = await client.post(
            "/cases",
            json={
                "case_number": case_number,
                "alert_type": "TRANSACTION_MONITORING",
                "alert_payload": {"rule_id": "TM-001"},
                "subject_party_id": "P-SUBJECT-API",
                "subject_party_name": "API Test Subject",
                "priority": "HIGH",
                "assigned_analyst_id": "analyst.test",
                "created_by": "analyst.test",
            },
        )
        assert r.status_code == 201, r.text
        case = r.json()
        case_id = case["id"]

        # ---- 2. Initial Assessment + approve -------------------------------
        r = await client.post(
            f"/cases/{case_id}/agents/INITIAL_ASSESSMENT/trigger", json={}
        )
        assert r.status_code == 202, r.text
        ia_run = r.json()
        assert ia_run["status"] == "AWAITING_REVIEW"

        r = await client.post(f"/agents/runs/{ia_run['id']}/approve")
        assert r.status_code == 200, r.text

        # ---- 3. Transaction Enrichment + verify the gate it opens ----------
        r = await client.post(
            f"/cases/{case_id}/agents/TRANSACTION_ENRICHMENT/trigger", json={}
        )
        assert r.status_code == 202, r.text
        txn_run = r.json()

        r = await client.get(f"/cases/{case_id}")
        assert r.status_code == 200
        state = r.json()
        gates = [g for g in state["gates"] if g["status"] == "OPEN_REQUIRED"]
        assert len(gates) == 1
        gate = gates[0]
        parties = state["parties"]
        assert len(parties) == 2

        r = await client.post(f"/agents/runs/{txn_run['id']}/approve")
        assert r.status_code == 200

        # ---- 4. Verify each party + resolve the gate -----------------------
        for party in parties:
            r = await client.post(f"/parties/{party['id']}/verify")
            assert r.status_code == 200, r.text
            assert r.json()["verified"] is True

        r = await client.post(
            f"/gates/{gate['id']}/resolve",
            json={"status": "APPROVED", "notes": "OK"},
        )
        assert r.status_code == 200, r.text

        # ---- 5. Due Diligence + Case Analysis ------------------------------
        r = await client.post(
            f"/cases/{case_id}/agents/DUE_DILIGENCE/trigger", json={}
        )
        assert r.status_code == 202, r.text
        dd_run = r.json()
        await client.post(f"/agents/runs/{dd_run['id']}/approve")

        r = await client.post(
            f"/cases/{case_id}/agents/CASE_ANALYSIS/trigger", json={}
        )
        assert r.status_code == 202, r.text
        ca_run = r.json()
        narrative_id = ca_run["output_payload"]["narrative_id"]

        await client.post(f"/agents/runs/{ca_run['id']}/approve")

        # ---- 6. Submit narrative + verify case is locked ------------------
        r = await client.post(f"/narratives/{narrative_id}/submit")
        assert r.status_code == 200, r.text
        submitted = r.json()
        assert submitted["submitted"] is True
        assert submitted["locked"] is True

        r = await client.get(f"/cases/{case_id}")
        assert r.status_code == 200
        final_state = r.json()
        assert final_state["case"]["locked"] is True
        assert final_state["case"]["status"] == "SUBMITTED"

        # ---- 7. Audit chain integrity --------------------------------------
        r = await client.get(f"/cases/{case_id}/audit/verify")
        assert r.status_code == 200
        verify = r.json()
        assert verify["ok"] is True
        assert verify["first_bad_id"] is None


async def test_missing_analyst_header_is_unauthorized(api_app, case_number: str) -> None:
    """Sanity check: mutating endpoints reject calls without `X-Analyst-Id`."""
    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://aml-test"
    ) as client:
        r = await client.post(
            "/cases",
            json={
                "case_number": case_number,
                "alert_type": "TRANSACTION_MONITORING",
                "alert_payload": {},
                "subject_party_id": "P",
                "subject_party_name": "X",
                "priority": "LOW",
                "created_by": "x",
            },
        )
        assert r.status_code == 401
