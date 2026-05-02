# ADK State, Session, and Memory Skill

Use ADK state concepts correctly.

## Session

Use Session for the active conversation or investigation run.

Examples:

- Current AML case
- Current party under review
- Current analyst workflow
- Current user interaction

## State

Use State for case-scoped runtime data.

Examples:

- `case_id`
- `alert_id`
- `customer_profile`
- `transaction_summary`
- `counterparty_priority_list`
- `evidence_map`
- `risk_score`

## Memory

Use Memory only for approved long-term reusable knowledge.

Examples:

- AML policy summaries
- Investigation playbooks
- Typology definitions
- Approved red flag taxonomy
- Prior reusable generic investigation patterns

Do not store sensitive case-specific findings in long-term memory unless explicitly approved.
