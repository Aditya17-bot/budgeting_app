"""
services/classifier.py
-----------------------
Classifies SMS messages into transaction types (Income / Expense) and
spending categories. Uses an ML pipeline when available, with a
keyword/regex fallback that is always available.

Public surface:
    classify_transaction_type(message)  -> "Income" | "Expense"
    classify_category(message)          -> str
    classify_category_by_keywords(message) -> str
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import joblib

# ---------------------------------------------------------------------------
# Transaction-type keywords
# NOTE: institutional/fee/student terms deliberately excluded here —
#       they appear in both debit and credit SMS and are classified by
#       direction keywords instead.
# ---------------------------------------------------------------------------

_INCOME_KEYWORDS: list[str] = [
    "credited",
    "received",
    "recieved",
    "refund",
    "reversal",
    "reversed",
    "cashback",
    "deposited",
    "added",
    "bonus",
    "reward",
    "salary",
    "amount credited",
    "has been credited",
    "has been deposited",
    "inr credited",
    "rs credited",
    "₹ credited",
    "received inr",
    "received rs",
    "received ₹",
    "payment received",
]

# Regex patterns that strongly indicate an inbound credit.
_INCOME_PATTERNS: list[str] = [
    r"\b(?:credited?|deposited?|received?|added|credit|deposit)\b.*\b(?:to|in)\s+(?:your|account)",
    r"\b(?:your|account)\s+(?:has\s+)?(?:been\s+)?(?:credited?|deposited?|received?)",
    r"\b(?:amount|sum|total)\s+of\s+[\d,]+\s*(?:rs|inr|₹)\s+(?:credited?|deposited?|received?)",
    r"\b[\d,]+\s*(?:rs|inr|₹)\s+(?:credited?|deposited?|received?|added)",
    r"\bupi:\d+.*credited",
    r"\bcredited.*upi:\d+",
]

# Regex patterns that strongly indicate an outbound debit.
_EXPENSE_PATTERNS: list[str] = [
    r"\b(?:debited?|deducted?|charged|spent|paid|withdrawn|used)\b",
    r"\b(?:from|sent|transfer(?:red)?)\s+(?:your|account)",
    r"\bpurchase\s+of\b",
    r"\bbill\s+payment\b",
    r"\bemi\s+payment\b",
    r"\btransaction\s+declined\b",
    r"\bdomestic\/international\s+transactions\b",
    r"\bblocked\s+\d+",
    r"\bautopay\s+for\b",
    r"\bmandate\s+auto\s+pay\b",
]

# ---------------------------------------------------------------------------
# Category keywords
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Food": [
        "zomato", "swiggy", "restaurant", "cafe", "pizza", "burger",
        "dining", "food", "domino", "kfc", "mcdonald", "starbucks",
        "cafe coffee day", "barbeque", "biryani",
    ],
    "Travel": [
        "uber", "ola", "metro", "bus", "train", "flight", "cab",
        "rapido", "redbus", "irctc", "makemytrip", "goibibo", "cleartrip",
        "airport", "toll",
    ],
    "Shopping": [
        "amazon", "flipkart", "myntra", "ajio", "nykaa", "store", "mall",
        "shopping", "meesho", "tata cliq", "reliance", "big bazaar",
    ],
    "Entertainment": [
        "netflix", "youtube", "spotify", "prime video", "hotstar",
        "sony liv", "voot", "altbalaji", "zee5", "bookmyshow",
        "streaming", "subscription", "premium",
    ],
    "Bills": [
        "electricity", "recharge", "wifi", "gas", "water", "broadband",
        "dth", "bill payment", "postpaid", "prepaid", "jio", "airtel",
        "vi ", "bsnl", "bescom", "tangedco",
    ],
    "Health": [
        "pharmacy", "hospital", "medical", "clinic", "doctor", "meds",
        "practo", "netmeds", "pharmeasy", "apollo", "diagnostic",
    ],
    "Education": [
        "fees", "tuition", "college", "university", "school",
        "course", "udemy", "coursera", "byju", "unacademy",
    ],
    "Personal": [
        "mr ", "mrs ", "shri ", "smt ", "transfer", "sent to",
        "paid to", "gift", "personal",
    ],
    "Other": [
        "fee", "charge", "charges", "interest", "imps",
        "neft", "rtgs",
    ],
}

# ---------------------------------------------------------------------------
# Model paths
# ---------------------------------------------------------------------------

_BASE_DIR   = Path(__file__).resolve().parents[1]
_MODELS_DIR = _BASE_DIR / "models"
_ML_DIR     = _BASE_DIR / "ml"

_MODEL_PATHS: list[Path] = [
    _MODELS_DIR / "sms_classifier (2).joblib",
    _ML_DIR     / "sms_classifier (2).joblib",
    _ML_DIR     / "model.pkl",
    _MODELS_DIR / "category_pipeline.joblib",
    _MODELS_DIR / "category_pipeline.pkl",
    _MODELS_DIR / "category_model.joblib",
    _MODELS_DIR / "category_model.pkl",
]

_VECTORIZER_PATHS: list[Path] = [
    _MODELS_DIR / "category_vectorizer.joblib",
    _MODELS_DIR / "category_vectorizer.pkl",
    _ML_DIR     / "category_vectorizer.joblib",
    _ML_DIR     / "category_vectorizer.pkl",
]

# Module-level singletons — loaded once on first use.
_CATEGORY_PIPELINE:   object = None
_CATEGORY_MODEL:      object = None
_CATEGORY_VECTORIZER: object = None
_MODEL_LOAD_ATTEMPTED: bool  = False

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_transaction_type(message: str) -> str:
    """
    Return ``"Income"`` or ``"Expense"`` for *message*.

    Resolution order:
    1. Explicit debit + credit together → Expense (debit takes priority).
    2. Income keyword match → Income.
    3. Income regex pattern match → Income.
    4. Expense regex pattern match → Expense.
    5. Default → Expense.
    """
    if not message:
        return "Expense"

    text = message.lower()

    # When both directions appear, the debit signal wins.
    if "debited" in text and "credited" in text:
        return "Expense"

    for keyword in _INCOME_KEYWORDS:
        if keyword in text:
            return "Income"

    for pattern in _INCOME_PATTERNS:
        if re.search(pattern, text):
            return "Income"

    for pattern in _EXPENSE_PATTERNS:
        if re.search(pattern, text):
            return "Expense"

    return "Expense"


def classify_category(message: str) -> str:
    """Return the spending category for *message*, using ML then keyword fallback."""
    prediction = _predict_category_with_model(message)
    return prediction if prediction else classify_category_by_keywords(message)


def classify_category_by_keywords(message: str) -> str:
    """Pure keyword/regex category classifier — no ML dependency."""
    text = message.lower() if message else ""

    # Personal transfers often mention a person's name before UPI/credited.
    _PERSONAL_PATTERNS = [
        r"\bmrs?\s+[a-z]+",
        r"\bshri\s+[a-z]+",
        r"\bsmt\s+[a-z]+",
        r"\bfrom\s+[a-z\s]+\s+upi:",
        r"\b[a-z\s]+\s+upi:",
    ]
    for pattern in _PERSONAL_PATTERNS:
        if re.search(pattern, text):
            return "Personal"

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if re.search(r"\b" + re.escape(keyword.strip()) + r"\b", text):
                return category

    return "Other"


# ---------------------------------------------------------------------------
# ML model — lazy loader
# ---------------------------------------------------------------------------


def _predict_category_with_model(message: str) -> Optional[str]:
    if not message or not str(message).strip():
        return None

    _load_category_model()

    if _CATEGORY_PIPELINE is not None:
        try:
            return _normalize_category_label(_CATEGORY_PIPELINE.predict([message])[0])
        except Exception:
            return None

    if _CATEGORY_MODEL is not None and _CATEGORY_VECTORIZER is not None:
        try:
            features = _CATEGORY_VECTORIZER.transform([message])
            return _normalize_category_label(_CATEGORY_MODEL.predict(features)[0])
        except Exception:
            return None

    return None


def _load_category_model() -> None:
    global _CATEGORY_PIPELINE, _CATEGORY_MODEL, _CATEGORY_VECTORIZER, _MODEL_LOAD_ATTEMPTED

    if _MODEL_LOAD_ATTEMPTED:
        return
    _MODEL_LOAD_ATTEMPTED = True

    for path in _MODEL_PATHS:
        if not path.exists():
            continue
        try:
            loaded = joblib.load(path)
        except Exception:
            continue

        if hasattr(loaded, "predict"):
            if hasattr(loaded, "named_steps") or "Pipeline" in type(loaded).__name__:
                _CATEGORY_PIPELINE = loaded
                return
            _CATEGORY_MODEL = loaded
            break

    if _CATEGORY_MODEL is not None:
        for path in _VECTORIZER_PATHS:
            if not path.exists():
                continue
            try:
                loaded = joblib.load(path)
                if hasattr(loaded, "transform"):
                    _CATEGORY_VECTORIZER = loaded
                    return
            except Exception:
                continue


def _normalize_category_label(label: object) -> Optional[str]:
    if label is None:
        return None
    text = str(label).strip()
    if not text:
        return None
    normalized = text.title()
    return normalized if normalized in CATEGORY_KEYWORDS else text