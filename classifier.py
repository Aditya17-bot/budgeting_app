import re

INCOME_KEYWORDS = ["credited", "received"]

CATEGORY_KEYWORDS = {
    "Food": ["zomato", "swiggy", "restaurant", "cafe"],
    "Travel": ["uber", "ola", "metro", "bus"],
    "Shopping": ["amazon", "flipkart", "myntra"],
    "Bills": ["electricity", "recharge", "wifi", "gas"],
    "Health": ["pharmacy", "hospital", "medical"],
}


def classify_transaction_type(message: str) -> str:
    text = message.lower() if message else ""
    for word in INCOME_KEYWORDS:
        if word in text:
            return "Income"
    return "Expense"


def classify_category(message: str) -> str:
    text = message.lower() if message else ""
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if re.search(r"\b" + re.escape(keyword) + r"\b", text):
                return category
    return "Other"
