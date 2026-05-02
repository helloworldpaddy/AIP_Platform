# ADK Tool Engineering Skill

All ADK tools must be implemented as plain Python functions.

Required:

- Strong type hints
- Clear docstrings
- JSON-serializable input and output
- Explicit error handling
- Deterministic behavior where possible
- No hidden side effects

Example:

```python
def search_case_transactions(case_id: str, max_results: int = 100) -> dict:
    """
    Search transactions for an AML investigation case.

    Args:
        case_id: Unique AML case identifier.
        max_results: Maximum number of transactions to return.

    Returns:
        Dictionary containing transactions, metadata, and source references.
    """
    return {
        "case_id": case_id,
        "transactions": [],
        "source": "case_transaction_store"
    }
```

Rules:

1. Do not put business logic only inside prompts.
2. Tools should enforce input validation.
3. Tools should return structured data.
4. Tool errors must be visible to the agent.
5. Every tool output should include source metadata where applicable.
