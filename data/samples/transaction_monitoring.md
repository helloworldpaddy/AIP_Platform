# Transaction Monitoring Procedures (Demo)

## Real-time screening

All outbound wire transfers above USD 10,000 are screened in real time
against the OFAC SDN list. Matches generate a TM-HIT alert and hold the
transaction pending review by the Level-2 analyst.

## Pattern detection

Automated rules flag:
- Round-dollar wire transfers to high-risk jurisdictions
- Rapid fund movement between unrelated accounts (layering)
- Cash deposits split across multiple branches on the same day
  (structuring / smurfing)

## Case management

Each TM-HIT becomes a case in the AML platform. Investigators gather
KYC documentation, beneficial ownership, and transaction history.
Cases must be closed within 30 days with one of: cleared, escalated
to MLRO, or filed as an STR.
