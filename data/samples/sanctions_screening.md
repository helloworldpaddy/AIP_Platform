# Sanctions Screening Procedure (Demo)

All new customers must be screened at onboarding against:
- OFAC SDN list
- EU Consolidated Financial Sanctions list
- UK OFSI consolidated list
- UN Security Council consolidated list

True matches are escalated to the MLRO within 24 hours. Partial matches
(fuzzy name hits) are reviewed by a Level-2 analyst and dispositioned
as true match, false positive, or further-evidence-required.

Screening is re-run daily against all active customers. Any new match
against an existing customer is treated as a Priority-1 case.
