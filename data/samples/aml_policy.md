# Sample AML Policy (Demo)

This is a non-normative sample document used to exercise the ingestion and
retrieval pipeline. Do not use for actual compliance guidance.

## Scope

This policy applies to all customer onboarding and transaction monitoring
activities conducted by ACME Financial Services.

## Sanctions Screening

All new customers are screened against the OFAC SDN list, the EU
consolidated sanctions list, and the UK OFSI list prior to onboarding.
Matches are escalated to the MLRO within one business day.

High-risk jurisdictions — including Iran, North Korea, Syria, and Cuba —
trigger enhanced due diligence (EDD). Beneficial ownership must be
documented for any entity with exposure to these jurisdictions.

## Beneficial Ownership

For every corporate customer, the ultimate beneficial owner (UBO) — any
natural person owning or controlling 25% or more of the entity — must be
identified. Shell companies and letterbox companies require EDD
regardless of ownership threshold.

## Politically Exposed Persons (PEP)

PEPs and their close associates are subject to senior management
approval before onboarding. Ongoing monitoring reviews are conducted
every 6 months for PEP accounts.

## Transaction Monitoring

Patterns flagged for review include:
- Structuring (smurfing): multiple transactions just below reporting thresholds
- Layering: rapid movement across unrelated accounts
- Wire transfers to shell companies in secrecy jurisdictions
- Unexplained cash-intensive deposits

## Reporting

Suspicious activity is reported via a Suspicious Transaction Report (STR)
to the relevant Financial Intelligence Unit within 30 days of detection.
