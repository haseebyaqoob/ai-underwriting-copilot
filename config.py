
# ── Confidence ────────────────────────────────────────────────────────────
DEFAULT_CONFIDENCE_THRESHOLD = 0.85

# ── Utility bill field aliases ──────────────────────────────────────────────
# Canonical field -> list of label variants that might appear on the bill
# (case-insensitive, fuzzy-matched — these don't need to be exhaustive,
# just representative; fuzzy matching handles OCR typos and partial hits).
UTILITY_BILL_FIELD_ALIASES = {
    "amount_payable": [
        "amount payable", "payable amount", "total amount", "amount due",
        "bill amount", "net payable", "total payable",
    ],
    "due_date": [
        "due date", "pay by", "payment due date", "last date", "due by",
    ],
    "issue_date": [
        "issue date", "bill issue date", "invoice date",
    ],
    "account_number": [
        "account number", "acc no", "account no", "reference number",
        "consumer number", "customer id",
    ],
    "current_units": [
        "units consumed", "current units", "units this month", "kwh consumed",
        "current month",
    ],
    "last_month_units": [
        "last month",
    ],
    "customer_name": [
        "customer name", "consumer name", "name", "billed to",
    ],
    "billing_history": [
        "billing history", "consumption history", "previous bills",
    ],
    "payment_history": [
        "payment history", "payments received", "previous payments",
    ],
}

# Regex shape expected for each field's *value* (used to find the nearest
# value-shaped text near a matched label, rather than trusting position).
UTILITY_BILL_VALUE_PATTERNS = {
    "amount_payable": r"[\d,]+(?:\.\d{1,2})?",
    "due_date": r"\d{1,2}[-/ ][A-Za-z0-9]{2,9}[-/ ]\d{2,4}",
    "account_number": r"[A-Za-z0-9\-]{6,20}",
    "current_units": r"[\d,]+(?:\.\d{1,2})?",
    "customer_name": r"[A-Za-z][A-Za-z .'\-]{2,60}",
}

PROVIDER_DETECTION_KEYWORDS = {
    "K-Electric": ["k-electric", "k electric", "ke bill", "kelectric"],
    # add more providers here as they're onboarded, e.g.:
    # "SEPCO": ["sepco", "sukkur electric"],
}

# ── Wallet statement field aliases ─────────────────────────────────────────
WALLET_BALANCE_ALIASES = ["balance", "available balance", "wallet balance", "current balance"]

WALLET_APP_KEYWORDS = {
    "Easypaisa": ["easypaisa", "easy paisa"],
    "JazzCash": ["jazzcash", "jazz cash"],
}

# Direction keywords, per app, since Easypaisa/JazzCash phrase things differently.
# "credit" = money in, "debit" = money out.
WALLET_DIRECTION_KEYWORDS = {
    "Easypaisa": {
        "credit": ["received", "cash in", "deposit", "refund"],
        "debit": ["sent", "payment", "transfer", "bill payment", "withdraw", "purchase"],
    },
    "JazzCash": {
        "credit": ["received", "cash in", "deposit", "refund"],
        "debit": ["sent", "payment", "transfer", "mobile load", "withdraw", "purchase"],
    },
    "_default": {
        "credit": ["received", "cash in", "deposit", "credited", "refund", "+"],
        "debit": ["sent", "payment", "transfer", "debited", "withdraw", "purchase", "-"],
    },
}

DATE_HEADER_PATTERN = r"\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}"
TRANSACTION_AMOUNT_PATTERN = r"[+\-]?\s?(?:Rs\.?|PKR)?\s?[\d,]+(?:\.\d{1,2})?"

# ── Fuzzy matching tolerance ────────────────────────────────────────────────
# Minimum similarity ratio (0-1) for a detected label to count as a match
# against an alias, to tolerate OCR typos and partial reads.
FUZZY_MATCH_THRESHOLD = 0.78

# Supported top-level document type routing. "khata" is intentionally a stub —
# see extractors/khata_stub.py — this pass does not implement handwritten
# ledger extraction.
SUPPORTED_DOCUMENT_TYPES = ["utility_bills", "wallet_statements", "khata"]
