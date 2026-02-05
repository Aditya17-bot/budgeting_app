import re
import pandas as pd

from classifier import classify_transaction_type, classify_category

KEYWORDS = [
    "spent",
    "debit",
    "debited",
    "paid",
    "credited",
    "received",
    "withdrawn",
    "purchase",
    "upi",
    "txn",
    "transaction",
]

AMOUNT_REGEX = re.compile(r"\b(?:rs\.?|inr)\s*([0-9,]+(?:\.\d{1,2})?)", re.IGNORECASE)


def is_financial_sms(message: str) -> bool:
    if not message:
        return False
    text = message.lower()
    if not any(k in text for k in KEYWORDS):
        return False
    return AMOUNT_REGEX.search(text) is not None


def extract_amount(message: str):
    match = AMOUNT_REGEX.search(message or "")
    if not match:
        return None
    amount_str = match.group(1).replace(",", "")
    try:
        return float(amount_str)
    except ValueError:
        return None


def extract_merchant(message: str) -> str:
    if not message:
        return ""
    text = re.sub(r"\s+", " ", message).strip()
    patterns = [
        r"\b(?:at|to|from|by|for|merchant|payee)\s+([A-Za-z0-9&\-\._ ]{2,40})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            candidate = re.split(
                r"\b(?:on|ref|txn|transaction|id|via)\b", candidate, flags=re.IGNORECASE
            )[0].strip()
            return candidate
    return ""


def coerce_datetime(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        sample = series.dropna().iloc[0] if not series.dropna().empty else None
        if sample is None:
            return pd.to_datetime(series, errors="coerce")
        unit = "s"
        if sample > 1e12:
            unit = "ms"
        elif sample > 1e10:
            unit = "ms"
        return pd.to_datetime(series, unit=unit, errors="coerce")
    return pd.to_datetime(series, errors="coerce")


def process_sms_dataframe(
    df: pd.DataFrame,
    message_col: str,
    date_col: str,
    sender_col: str | None = None,
) -> pd.DataFrame:
    records = []
    for _, row in df.iterrows():
        message = str(row.get(message_col, "") or "")
        if not is_financial_sms(message):
            continue
        amount = extract_amount(message)
        if amount is None:
            continue
        sender = ""
        if sender_col:
            sender = str(row.get(sender_col, "") or "").strip()
        merchant = extract_merchant(message)
        if not merchant and sender:
            merchant = sender
        records.append(
            {
                "date": row.get(date_col),
                "amount": amount,
                "transaction_type": classify_transaction_type(message),
                "category": classify_category(message),
                "merchant": merchant,
                "original_message": message,
            }
        )
    result = pd.DataFrame(records)
    if not result.empty:
        result["date"] = coerce_datetime(result["date"])
    return result
