"""PII masking for log output (spec §3.D — Data Masking).

The narrative + evidence_ledger keep PII intact for the investigation; this
utility is invoked only when text is about to leave the trust boundary
(structured logs, OpenTelemetry attributes, error messages bubbled to the UI).

Patterns covered:
    * Email addresses
    * Phone numbers (E.164-ish, plus common local formats)
    * SSN / national-ID-like 9-digit blocks
    * IBAN-style account numbers
    * Credit-card-like 13–19 digit blocks (with Luhn double-check to reduce FPs)
    * Generic long digit runs (>= 9) — last-resort catch
    * Common name keys in dict payloads (`first_name`, `dob`, `passport`, …)

Calling pattern:

    log.info("agent.completed", extra={"output": mask_text(json.dumps(output))})
    safe_payload = mask_dict(payload)
"""

from __future__ import annotations

import re
from typing import Any

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(
    r"""(?x)
    (?<!\d)                   # not preceded by a digit
    (?:\+?\d{1,3}[\s\-\.]?)?  # optional country code
    (?:\(?\d{2,4}\)?[\s\-\.]?)
    \d{3,4}[\s\-\.]?
    \d{3,4}
    (?!\d)
    """
)
_SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
_LONG_DIGITS_RE = re.compile(r"(?<!\d)\d{9,19}(?!\d)")

_PII_KEYS = frozenset(
    {
        "first_name",
        "last_name",
        "full_name",
        "name",
        "dob",
        "date_of_birth",
        "ssn",
        "tax_id",
        "passport",
        "passport_number",
        "national_id",
        "phone",
        "phone_number",
        "email",
        "address",
        "street",
        "iban",
        "account_number",
        "card_number",
        "pan",
    }
)


def _luhn_ok(digits: str) -> bool:
    """Standard Luhn check; we only mask 13–19-digit runs that pass it."""
    total = 0
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        n = ord(ch) - 48
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _mask_value(value: str, *, keep_last: int = 0) -> str:
    if not value:
        return value
    if keep_last and len(value) > keep_last:
        return "*" * (len(value) - keep_last) + value[-keep_last:]
    return "*" * len(value)


def mask_text(text: str) -> str:
    """Return `text` with every PII pattern redacted in place."""
    if not text:
        return text

    def _email_sub(m: re.Match[str]) -> str:
        local, _, domain = m.group(0).partition("@")
        return f"{local[0]}***@{domain}"

    def _phone_sub(m: re.Match[str]) -> str:
        return _mask_value(m.group(0), keep_last=2)

    def _digit_sub(m: re.Match[str]) -> str:
        run = m.group(0)
        # Only mask card-length runs that look like real cards.
        if 13 <= len(run) <= 19 and not _luhn_ok(run):
            return run
        return _mask_value(run, keep_last=4)

    out = _EMAIL_RE.sub(_email_sub, text)
    out = _SSN_RE.sub("***-**-****", out)
    out = _IBAN_RE.sub(lambda m: _mask_value(m.group(0), keep_last=4), out)
    out = _PHONE_RE.sub(_phone_sub, out)
    out = _LONG_DIGITS_RE.sub(_digit_sub, out)
    return out


def mask_dict(payload: Any) -> Any:
    """Recursively redact a JSON-like structure.

    * Strings → `mask_text`
    * Dict values whose key is in `_PII_KEYS` → fully masked
    * Lists / tuples → recursed element-wise
    Other scalars are returned untouched.
    """
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for k, v in payload.items():
            if isinstance(k, str) and k.lower() in _PII_KEYS:
                if isinstance(v, str):
                    out[k] = _mask_value(v, keep_last=2)
                elif isinstance(v, (int, float)):
                    out[k] = "***"
                else:
                    out[k] = mask_dict(v)
            else:
                out[k] = mask_dict(v)
        return out
    if isinstance(payload, (list, tuple)):
        return [mask_dict(v) for v in payload]
    if isinstance(payload, str):
        return mask_text(payload)
    return payload
