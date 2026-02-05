import re

INCOME_KEYWORDS = [
    "credited",
    "received",
    "recieved",  # Adding common misspelling
    "refund",
    "reversal",
    "reversed",
    "cashback",
    "credit",
    "deposited",
    "added",
    "bonus",
    "reward",
    "salary",
    "payment received",
    "amount credited",
    "has been credited",
    "has been deposited",
    "inr credited",
    "rs credited",
    "₹ credited",
    "received inr",
    "received rs",
    "received ₹",
    "payment of rs",
    "payment of inr",
    "payment of ₹",
    "payment received",
    "student",
    "reference number",
    "vt op",  # VIT fee payment pattern
    "vit",     # VIT specific
    "bce",     # BCE code for education
    "fees",
    "tuition",
]

CATEGORY_KEYWORDS = {
    "Food": [
        "zomato",
        "swiggy",
        "restaurant",
        "cafe",
        "pizza",
        "burger",
        "dining",
        "food",
        "domino's",
        "kfc",
        "mcdonald",
        "starbucks",
        "cafe coffee day",
    ],
    "Travel": [
        "uber",
        "ola",
        "metro",
        "bus",
        "train",
        "flight",
        "cab",
        "rapido",
        "redbus",
        "irctc",
        "makemytrip",
        "goibibo",
        "cleartrip",
    ],
    "Shopping": [
        "amazon",
        "flipkart",
        "myntra",
        "ajio",
        "nykaa",
        "store",
        "mall",
        "shopping",
        "meesho",
        "ajio",
        "tata cliq",
    ],
    "Entertainment": [
        "netflix",
        "youtube",
        "spotify",
        "prime video",
        "hotstar",
        "sony liv",
        "voot",
        "altbalaji",
        "zee5",
        "music",
        "video",
        "streaming",
        "subscription",
        "premium",
        "renewal",
    ],
    "Bills": [
        "electricity",
        "recharge",
        "wifi",
        "gas",
        "water",
        "broadband",
        "dth",
        "bill",
        "postpaid",
        "prepaid",
        "jio",
        "airtel",
        "vi",
        "bsnl",
    ],
    "Health": [
        "pharmacy",
        "hospital",
        "medical",
        "clinic",
        "doctor",
        "meds",
        "practo",
        "netmeds",
        "pharmeasy",
        "apollo",
    ],
    "Education": [
        "student",
        "reference number",
        "vt op",
        "vit",
        "bce",
        "fees",
        "tuition",
        "payment of rs",
        "payment of inr",
        "payment of ₹",
        "received",
        "receipt",
    ],
    "Personal": [
        "mr ",
        "mrs ",
        "shri ",
        "smt ",
        "transfer",
        "sent to",
        "paid to",
        "gift",
        "personal",
    ],
    "Other": [
        "fee",
        "charge",
        "charges",
        "interest",
        "imps",
        "neft",
        "rtgs",
        "upi",
        "txn",
        "transaction",
    ],
}


def classify_transaction_type(message: str) -> str:
    if not message:
        return "Expense"
    
    text = message.lower()
    
    # Check if both debited and credited are present (mixed message)
    if 'debited' in text and 'credited' in text:
        return "Expense"  # Always classify mixed messages as expense
    
    # Check for income indicators (only if not mixed)
    for word in INCOME_KEYWORDS:
        if word in text:
            return "Income"
    
    # Additional checks for common credit patterns
    credit_patterns = [
        r'\b(?:credited?|deposited?|received?|added|credit|deposit)\b.*\b(?:to|in)\s+(?:your|account)',
        r'\b(?:your|account)\s+(?:has\s+)?(?:been\s+)?(?:credited?|deposited?|received?|credited)',
        r'\b(?:amount|sum|total)\s+of\s+[\d,]+\s*(?:rs|inr|₹)\s+(?:credited?|deposited?|received?)',
        r'\b[\d,]+\s*(?:rs|inr|₹)\s+(?:credited?|deposited?|received?|added)',
        r'\bupi:\d+.*credited',
        r'\bcredited.*upi:\d+',
    ]
    
    for pattern in credit_patterns:
        if re.search(pattern, text):
            return "Income"
    
    # Enhanced expense detection patterns
    expense_patterns = [
        r'\b(?:debited?|deducted?|charged|spent|paid|withdrawn|used)\b',
        r'\b(?:from|sent|transfer)\s+(?:your|account)',
        r'\b(?:towards|for)\s+[a-z\s]+',  # "towards NETFLIX", "for Amazon"
        r'\b(?:at|in|on)\s+[a-z\s]+',  # "at Amazon", "in Swiggy"
        r'\bpurchase\s+of',
        r'\bbill\s+payment',
        r'\bemi\s+payment',
        r'\btransaction\s+declined',
        r'\bdomestic\/international\s+transactions',
        r'\bvisit\s+icici\.co',
        r'\bcreate\s+mandate',
        r'\bautopay\s+for',
        r'\bmandate\s+auto\s+pay',
        r'\bretrieval\s+ref',
        r'\bblocked\s+\d+',
        r'\bsms\s+block',
        r'\bcall\s+\d+\s+for\s+dispute',
    ]
    
    for pattern in expense_patterns:
        if re.search(pattern, text):
            return "Expense"
    
    return "Expense"  # Default to expense for safety


def classify_category(message: str) -> str:
    text = message.lower() if message else ""
    
    # Check for personal transfers first (names with mr/mrs)
    personal_patterns = [
        r'\bmrs?\s+[a-z\s]+',
        r'\bshri\s+[a-z\s]+',
        r'\bsmt\s+[a-z\s]+',
        r'\bfrom\s+[a-z\s]+\s+credited',
        r'\b[a-z\s]+\s+credited',
        r'\bdear\s+[a-z\s]+',
        r'\b[a-z\s]+\s+UPI:',
        r'\bfrom\s+[a-z\s]+\s+UPI:',
    ]
    
    for pattern in personal_patterns:
        if re.search(pattern, text):
            return "Personal"
    
    # Check other categories
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if re.search(r"\b" + re.escape(keyword) + r"\b", text):
                return category
    return "Other"
