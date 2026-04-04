"""
core/extractor.py
-----------------
Extracts structured transaction data (amount, type, merchant, date, category)
from raw SMS/notification text.

Public surface:
    extract_transaction(message, fallback_date) -> dict | None
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

import pandas as pd
import spacy
from spacy.matcher import Matcher

from services.classifier import classify_category

# ---------------------------------------------------------------------------
# NLP setup
# ---------------------------------------------------------------------------

_NLP = spacy.blank("en")
_MATCHER = Matcher(_NLP.vocab)
_MATCHER.add(
    "AMOUNT_PATTERN",
    [
        [{"LOWER": {"IN": ["rs", "rs.", "inr"]}}, {"LIKE_NUM": True}],
        [{"TEXT": "₹"}, {"LIKE_NUM": True}],
        [{"LIKE_NUM": True}, {"LOWER": {"IN": ["rs", "rs.", "inr"]}}],
    ],
)

# ---------------------------------------------------------------------------
# Compiled regexes
# ---------------------------------------------------------------------------

AMOUNT_REGEX = re.compile(
    r"(?i)(?:rs\.?|inr|₹)\s*([0-9][0-9,]*(?:\.\d{1,2})?)"
    r"|([0-9][0-9,]*(?:\.\d{1,2})?)\s*(?:rs\.?|inr|₹)"
)

DATE_REGEX = re.compile(
    r"(?i)\bon\s+"
    r"([0-9]{1,2}[-/ ]"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|[0-9]{1,2})"
    r"[-/ ][0-9]{2,4})"
)

_YEAR_SUFFIX_RE = re.compile(r"(?:19|20)?\d{2}$")

# ---------------------------------------------------------------------------
# Keyword sets
# ---------------------------------------------------------------------------

EXPENSE_KEYWORDS: frozenset[str] = frozenset(
    {"debited", "debit", "spent", "paid", "withdrawn", "deducted", "charged", "purchase"}
)
INCOME_KEYWORDS: frozenset[str] = frozenset(
    {"credited", "credit", "received", "refund", "reversal", "deposited", "cashback", "added"}
)

# Messages matching any of these substrings are silently dropped.
_IGNORE_CONTENT_PATTERNS: tuple[str, ...] = (
    "generalpurposecard",
    "generalpurposecardcarousel",
    '"message": {',
    "mediaurl",
    "suggestions",
    "openurl",
)

# Messages describing non-completed or future transactions are dropped.
_IGNORE_STATUS_PATTERNS: tuple[str, ...] = (
    "transaction was declined",
    "transactions are disabled",
    "will be debited",
)

# Merchant extraction patterns, keyed by transaction direction.
_MERCHANT_PATTERNS: dict[str, list[str]] = {
    "Expense": [
        r"(?i);\s*([A-Za-z][A-Za-z\s.&'-]{2,40}?)\s+credited\b",
        r"(?i)\btowards\s+([A-Za-z][A-Za-z0-9\s.&'-]{2,40}?)(?:\s+for\b|[.,;]|$)",
        r"(?i)\bat\s+([A-Za-z][A-Za-z0-9\s.&'-]{2,40}?)(?:\s+on\b|[.,;]|$)",
        r"(?i)\bfor\s+([A-Za-z][A-Za-z0-9\s.&'-]{2,40}?)(?:\s+credited\b|\s+on\b|[.,;]|$)",
    ],
    "Income": [
        r"(?i)\bfrom\s+([A-Za-z][A-Za-z\s.&'-]{2,40}?)(?:\s+upi:|[.,;]|-icici|$)",
        r"(?i)\bcredited\b.*?\bfrom\s+([A-Za-z][A-Za-z\s.&'-]{2,40}?)(?:\s+upi:|[.,;]|-icici|$)",
    ],
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_transaction(
    message: str,
    fallback_date: Optional[object] = None,
) -> Optional[dict]:
    """
    Parse *message* and return a structured transaction dict, or ``None`` if
    the message doesn't look like a financial transaction.

    Returned keys: amount, transaction_type, merchant, category, date, confidence.
    """
    if not message or not str(message).strip():
        return None

    text = str(message).strip()
    lowered = text.lower()

    if _should_ignore_message(lowered):
        return None

    doc = _NLP(text)
    if not _looks_like_transaction(doc, lowered):
        return None

    amount = _extract_amount(doc, text)
    transaction_type = _extract_transaction_type(lowered)
    if amount is None or transaction_type is None:
        return None

    merchant = _extract_merchant(text, transaction_type)
    parsed_date = _extract_date(text, fallback_date)
    category = classify_category(f"{merchant} {text}".strip())

    return {
        "amount": amount,
        "transaction_type": transaction_type,
        "merchant": merchant,
        "category": category,
        "date": parsed_date,
        "confidence": "medium",
    }


# ---------------------------------------------------------------------------
# Internal helpers — filtering
# ---------------------------------------------------------------------------


def _should_ignore_message(lowered: str) -> bool:
    if any(p in lowered for p in _IGNORE_CONTENT_PATTERNS):
        return True
    if any(p in lowered for p in _IGNORE_STATUS_PATTERNS):
        return True
    # Promotional opt-out messages that don't mention an actual movement of funds.
    if (
        "reply stop" in lowered
        and "debited" not in lowered
        and "credited" not in lowered
    ):
        return True
    return False


def _looks_like_transaction(doc, lowered: str) -> bool:
    has_amount = bool(_MATCHER(doc)) or bool(AMOUNT_REGEX.search(lowered))
    has_direction = bool(lowered and (EXPENSE_KEYWORDS | INCOME_KEYWORDS) & set(lowered.split()))
    return has_amount and has_direction


# ---------------------------------------------------------------------------
# Internal helpers — extraction
# ---------------------------------------------------------------------------


def _extract_amount(doc, text: str) -> Optional[float]:
    """Return the first parsable currency amount found in *doc* / *text*."""
    for _, start, end in _MATCHER(doc):
        value = _parse_amount(doc[start:end].text)
        if value is not None:
            return value

    match = AMOUNT_REGEX.search(text)
    if not match:
        return None

    for group in match.groups():
        if group:
            value = _parse_amount(group)
            if value is not None:
                return value

    return None


def _parse_amount(value: str) -> Optional[float]:
    """Strip currency symbols/labels from *value* and return a float, or None."""
    cleaned = (
        value
        .replace(",", "")
        .replace("rs.", "")
        .replace("rs", "")
        .replace("inr", "")
        .replace("₹", "")
        .strip()
    )
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _extract_transaction_type(lowered: str) -> Optional[str]:
    """
    Resolve whether *lowered* represents an Expense or Income.

    When both directions appear (e.g. "Rs 100 debited; Rs 50 cashback credited"),
    the message-level word boundary match for "debited"/"credited" breaks the tie.
    Defaults to "Expense" when the tie can't be broken, as debits are more common
    in mixed-signal messages.
    """
    has_expense = bool(EXPENSE_KEYWORDS & set(lowered.split()))
    has_income = bool(INCOME_KEYWORDS & set(lowered.split()))

    if has_expense and not has_income:
        return "Expense"
    if has_income and not has_expense:
        return "Income"
    if has_expense and has_income:
        padded = f" {lowered} "
        if " debited " in padded:
            return "Expense"
        if " credited " in padded:
            return "Income"
        return "Expense"  # safe default for ambiguous messages
    return None


def _extract_merchant(text: str, transaction_type: str) -> str:
    """Return a title-cased merchant name extracted from *text*, or empty string."""
    for pattern in _MERCHANT_PATTERNS.get(transaction_type, []):
        match = re.search(pattern, text)
        if match:
            return _clean_merchant(match.group(1))
    return ""


def _clean_merchant(value: str) -> str:
    merchant = re.sub(r"\s+", " ", value).strip(" .,-;:")
    merchant = re.sub(r"(?i)\bupi[:\s-].*$", "", merchant).strip(" .,-;:")
    return merchant.title()


def _extract_date(
    text: str,
    fallback_date: Optional[object],
) -> Optional[pd.Timestamp]:
    """
    Return an explicit date found in *text*, falling back to *fallback_date*.
    Year is inferred from *fallback_date* when the matched date string has none.
    """
    match = DATE_REGEX.search(text)
    if match:
        parsed = _coerce_date(match.group(1), fallback_date)
        if parsed is not None:
            return parsed
    return _coerce_date(fallback_date, fallback_date)


# ---------------------------------------------------------------------------
# Internal helpers — date coercion
# ---------------------------------------------------------------------------


def _coerce_date(
    value: Optional[object],
    fallback_date: Optional[object],
) -> Optional[pd.Timestamp]:
    if value is None or value == "":
        return None

    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        return None

    # Patch in the reference year when the string had no explicit year component.
    if isinstance(value, str) and not _contains_explicit_year(value):
        parsed = parsed.replace(year=_reference_year(fallback_date))

    return parsed


def _contains_explicit_year(value: str) -> bool:
    return bool(_YEAR_SUFFIX_RE.search(value.strip()))


def _reference_year(fallback_date: Optional[object]) -> int:
    """Extract a year from *fallback_date*, defaulting to the current year."""
    if isinstance(fallback_date, pd.Timestamp):
        return fallback_date.year
    if isinstance(fallback_date, (datetime, date)):
        return fallback_date.year

    parsed = pd.to_datetime(fallback_date, errors="coerce")
    return parsed.year if not pd.isna(parsed) else datetime.now().year