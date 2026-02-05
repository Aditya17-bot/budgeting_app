import re
import xml.etree.ElementTree as ET
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


def _extract_mms_text(mms_elem) -> str:
    parts = mms_elem.findall("./parts/part")
    text_parts = []
    for part in parts:
        content_type = (part.attrib.get("ct") or "").lower()
        if content_type.startswith("text/"):
            text = part.attrib.get("text") or ""
            if text:
                text_parts.append(text)
    if text_parts:
        return " ".join(text_parts).strip()
    return (mms_elem.attrib.get("sub") or "").strip()


def _extract_mms_sender(mms_elem) -> str:
    for addr in mms_elem.findall("./addrs/addr"):
        addr_type = addr.attrib.get("type")
        if addr_type == "137":
            return addr.attrib.get("address") or ""
    first = mms_elem.find("./addrs/addr")
    if first is not None:
        return first.attrib.get("address") or ""
    return mms_elem.attrib.get("address") or ""


def load_sms_xml(file_like) -> pd.DataFrame:
    tree = ET.parse(file_like)
    root = tree.getroot()
    rows = []

    for sms in root.findall("sms"):
        rows.append(
            {
                "date": sms.attrib.get("date"),
                "readable_date": sms.attrib.get("readable_date"),
                "address": sms.attrib.get("address"),
                "contact_name": sms.attrib.get("contact_name"),
                "body": sms.attrib.get("body"),
                "type": sms.attrib.get("type"),
                "kind": "sms",
            }
        )

    for mms in root.findall("mms"):
        rows.append(
            {
                "date": mms.attrib.get("date"),
                "readable_date": mms.attrib.get("readable_date"),
                "address": _extract_mms_sender(mms),
                "contact_name": mms.attrib.get("contact_name"),
                "body": _extract_mms_text(mms),
                "type": mms.attrib.get("msg_box") or mms.attrib.get("type"),
                "kind": "mms",
            }
        )

    return pd.DataFrame(rows)
