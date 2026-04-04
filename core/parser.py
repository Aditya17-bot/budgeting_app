"""
core/parser.py
--------------
Ingests raw SMS/MMS data — from DataFrames or XML backup files — and
produces a normalised transactions DataFrame.

Public surface:
    is_financial_sms(message)           -> bool
    extract_amount(message)             -> float | None
    extract_merchant(message)           -> str
    coerce_datetime(series)             -> pd.Series
    process_sms_dataframe(df, ...)      -> pd.DataFrame
    process_single_sms(message, ...)    -> pd.DataFrame
    load_sms_xml(file_like)             -> pd.DataFrame
"""

import re
import xml.etree.ElementTree as ET
from typing import Optional

import pandas as pd

from services.classifier import classify_transaction_type, classify_category
from core.extractor import extract_transaction

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FINANCIAL_KEYWORDS: tuple[str, ...] = (
    "spent", "debit", "debited", "paid", "credited", "received",
    "withdrawn", "purchase", "upi", "txn", "transaction",
)

_AMOUNT_REGEX = re.compile(
    r"\b(?:rs\.?|inr)\s*([0-9,]+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)

# Patterns that identify non-financial institutional messages (e.g. VIT portal
# notifications) that happen to contain numeric strings resembling amounts.
_NON_FINANCIAL_PATTERNS: tuple[re.Pattern, ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in [
        r"dear\s+student.*\d{10}[a-z0-9]+",   # VIT registration references
        r"reference\s+number.*\d{10}[a-z0-9]+",
        r"check\s+receipt.*vt\s*op",            # VTOP receipt messages
        r"bce\d+",                               # BCE institutional codes
        r"23bce\d+",
    ]
)

# Output column order for all processed DataFrames.
_OUTPUT_COLUMNS: list[str] = [
    "date", "amount", "transaction_type", "category", "merchant", "original_message",
]

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def is_financial_sms(message: str) -> bool:
    """Return True when *message* looks like a bank/wallet transaction alert."""
    if not message:
        return False

    text = message.lower()

    if any(pat.search(text) for pat in _NON_FINANCIAL_PATTERNS):
        return False

    if not any(kw in text for kw in _FINANCIAL_KEYWORDS):
        return False

    return _AMOUNT_REGEX.search(text) is not None


def extract_amount(message: str) -> Optional[float]:
    """Return the first currency amount found in *message*, or None."""
    match = _AMOUNT_REGEX.search(message or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def extract_merchant(message: str) -> str:
    """
    Return a rough merchant name from *message*, or an empty string.

    Strips trailing reference/ID tokens that commonly follow merchant names.
    """
    if not message:
        return ""

    text = re.sub(r"\s+", " ", message).strip()
    pattern = r"\b(?:at|to|from|by|for|merchant|payee)\s+([A-Za-z0-9&\-\._ ]{2,40})"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return ""

    candidate = match.group(1).strip()
    # Trim everything from reference/ID markers onward.
    candidate = re.split(
        r"\b(?:on|ref|txn|transaction|id|via)\b", candidate, flags=re.IGNORECASE
    )[0].strip()
    return candidate


def coerce_datetime(series: pd.Series) -> pd.Series:
    """
    Parse *series* to datetime, handling both Unix timestamps (seconds / ms)
    and ISO-style strings gracefully.
    """
    if not pd.api.types.is_numeric_dtype(series):
        return pd.to_datetime(series, errors="coerce")

    sample = series.dropna().iloc[0] if not series.dropna().empty else None
    if sample is None:
        return pd.to_datetime(series, errors="coerce")

    # Values above 1e10 are almost certainly milliseconds.
    unit = "ms" if sample > 1e10 else "s"
    return pd.to_datetime(series, unit=unit, errors="coerce")


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------


def process_sms_dataframe(
    df: pd.DataFrame,
    message_col: str,
    date_col: str,
    sender_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    Process every row of *df* and return a normalised transactions DataFrame.

    Rows that yield no transaction are silently skipped.  The extractor is
    tried first; the simpler regex-based path is used as a fallback.
    """
    records: list[dict] = []

    for _, row in df.iterrows():
        message = str(row.get(message_col) or "").strip()
        sender = str(row.get(sender_col) or "").strip() if sender_col else ""
        raw_date = row.get(date_col)

        record = _build_record_from_extractor(message, raw_date, sender)
        if record is None:
            record = _build_record_from_fallback(message, raw_date, sender)

        if record is not None:
            records.append(record)

    result = pd.DataFrame(records, columns=_OUTPUT_COLUMNS) if records else pd.DataFrame(columns=_OUTPUT_COLUMNS)
    if not result.empty:
        result["date"] = coerce_datetime(result["date"])
    return result


def process_single_sms(
    message: str,
    message_date=None,
    sender: Optional[str] = None,
) -> pd.DataFrame:
    """Convenience wrapper: process a single SMS string."""
    frame = pd.DataFrame([{"body": message, "date": message_date, "address": sender}])
    return process_sms_dataframe(frame, "body", "date", "address")


# ---------------------------------------------------------------------------
# Record builders (internal)
# ---------------------------------------------------------------------------


def _build_record_from_extractor(
    message: str,
    raw_date,
    sender: str,
) -> Optional[dict]:
    """Try the rich extractor; return a record dict or None."""
    extracted = extract_transaction(message, fallback_date=raw_date)
    if not extracted:
        return None

    return {
        "date": extracted.get("date") or raw_date,
        "amount": extracted.get("amount"),
        "transaction_type": extracted.get("transaction_type"),
        "category": extracted.get("category"),
        "merchant": extracted.get("merchant") or sender,
        "original_message": message,
    }


def _build_record_from_fallback(
    message: str,
    raw_date,
    sender: str,
) -> Optional[dict]:
    """
    Regex-only fallback for messages the extractor couldn't handle.
    Returns None when *message* isn't financial or has no parsable amount.
    """
    if not is_financial_sms(message):
        return None

    amount = extract_amount(message)
    if amount is None:
        return None

    merchant = extract_merchant(message) or sender

    return {
        "date": raw_date,
        "amount": amount,
        "transaction_type": classify_transaction_type(message),
        "category": classify_category(message),
        "merchant": merchant,
        "original_message": message,
    }


# ---------------------------------------------------------------------------
# XML loader (SMS Backup & Restore format)
# ---------------------------------------------------------------------------


def load_sms_xml(file_like) -> pd.DataFrame:
    """
    Parse an SMS Backup & Restore XML file and return a raw DataFrame
    (not yet transaction-processed — pass through process_sms_dataframe next).
    """
    root = ET.parse(file_like).getroot()
    rows: list[dict] = []

    for sms in root.findall("sms"):
        rows.append({
            "date": sms.attrib.get("date"),
            "readable_date": sms.attrib.get("readable_date"),
            "address": sms.attrib.get("address"),
            "contact_name": sms.attrib.get("contact_name"),
            "body": sms.attrib.get("body"),
            "type": sms.attrib.get("type"),
            "kind": "sms",
        })

    for mms in root.findall("mms"):
        rows.append({
            "date": mms.attrib.get("date"),
            "readable_date": mms.attrib.get("readable_date"),
            "address": _extract_mms_sender(mms),
            "contact_name": mms.attrib.get("contact_name"),
            "body": _extract_mms_text(mms),
            "type": mms.attrib.get("msg_box") or mms.attrib.get("type"),
            "kind": "mms",
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# MMS helpers (internal)
# ---------------------------------------------------------------------------


def _extract_mms_text(mms_elem) -> str:
    """
    Return the concatenated plain-text parts of an MMS element.
    Falls back to the ``sub`` (subject) attribute when no text parts exist.
    """
    text_parts = [
        part.attrib.get("text", "")
        for part in mms_elem.findall("./parts/part")
        if (part.attrib.get("ct") or "").lower().startswith("text/")
        and part.attrib.get("text")
    ]
    return " ".join(text_parts).strip() if text_parts else (mms_elem.attrib.get("sub") or "").strip()


def _extract_mms_sender(mms_elem) -> str:
    """
    Return the sender address from MMS address elements.
    Type 137 is the FROM address in the MMS PDU spec.
    """
    for addr in mms_elem.findall("./addrs/addr"):
        if addr.attrib.get("type") == "137":
            return addr.attrib.get("address") or ""

    first = mms_elem.find("./addrs/addr")
    if first is not None:
        return first.attrib.get("address") or ""

    return mms_elem.attrib.get("address") or ""