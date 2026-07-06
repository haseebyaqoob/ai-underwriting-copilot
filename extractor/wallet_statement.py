
from __future__ import annotations
import re
import config
from utils import fuzzy_label_match, find_nearest_value, make_field, safe_parse_amount


def detect_app(tokens) -> str:
    full_text = " ".join(t.text.lower() for t in tokens)
    for app, keywords in config.WALLET_APP_KEYWORDS.items():
        if any(kw in full_text for kw in keywords):
            return app
    return "unknown"


def extract_balance(tokens, threshold: float) -> dict:
    for tok in tokens:
        if fuzzy_label_match(tok.text, config.WALLET_BALANCE_ALIASES):
            value_tok = find_nearest_value(
                tok.bbox, tokens, config.TRANSACTION_AMOUNT_PATTERN,
                exclude_bboxes={tok.bbox}, max_distance=250,
            )
            if value_tok:
                # safe_parse_amount replaces the old bare
                # re.sub(r"[^\d.]", ...) + float(...) which raised ValueError
                # whenever OCR merged two adjacent numbers into one string
                # (e.g. two nearby amounts collapsing into ".49046.91").
                value = safe_parse_amount(value_tok.text)
                return make_field(value, value_tok.confidence, threshold,
                                   extra={"currency": "PKR"})
    return make_field(None, 0.0, threshold, extra={"reason": "balance label not found"})


def group_into_rows(tokens, row_gap: float = 18.0) -> list[list]:
    """Group tokens into horizontal rows by y-proximity — a lightweight
    stand-in for real layout clustering, used to approximate 'transaction
    cards' without assuming a fixed pixel grid."""
    if not tokens:
        return []
    sorted_tokens = sorted(tokens, key=lambda t: (t.bbox[1], t.bbox[0]))
    rows, current_row, current_y = [], [], None
    for tok in sorted_tokens:
        y_center = (tok.bbox[1] + tok.bbox[3]) / 2
        if current_y is None or abs(y_center - current_y) <= row_gap:
            current_row.append(tok)
            current_y = y_center if current_y is None else (current_y + y_center) / 2
        else:
            rows.append(current_row)
            current_row = [tok]
            current_y = y_center
    if current_row:
        rows.append(current_row)
    return rows


def classify_direction(row_text: str, app: str) -> str | None:
    keywords = config.WALLET_DIRECTION_KEYWORDS.get(app, config.WALLET_DIRECTION_KEYWORDS["_default"])
    text_lower = row_text.lower()
    if any(kw in text_lower for kw in keywords["credit"]):
        return "credit"
    if any(kw in text_lower for kw in keywords["debit"]):
        return "debit"
    return None


def extract_transactions(tokens, app: str, image_height: float | None, threshold: float) -> list[dict]:
    rows = group_into_rows(tokens)
    transactions = []
    current_date_header = None

    for i, row in enumerate(rows):
        row_text = " ".join(t.text for t in row)

        if re.search(config.DATE_HEADER_PATTERN, row_text):
            current_date_header = re.search(config.DATE_HEADER_PATTERN, row_text).group(0)
            continue  # a pure date-header row, not a transaction itself

        amount_match = re.search(config.TRANSACTION_AMOUNT_PATTERN, row_text)
        if not amount_match:
            continue  # not a transaction-shaped row

        direction = classify_direction(row_text, app)
        avg_conf = sum(t.confidence for t in row) / len(row) if row else 0.0

        # Cut-off row detection: a row touching the very top or bottom edge of
        # the image is likely visually cropped by the screen boundary.
        row_top = min(t.bbox[1] for t in row)
        row_bottom = max(t.bbox[3] for t in row)
        is_cutoff = False
        if image_height:
            edge_margin = image_height * 0.02
            is_cutoff = row_top <= edge_margin or row_bottom >= (image_height - edge_margin)

        # safe_parse_amount never raises — a malformed/merged number just
        # comes back as None (flagged, low-confidence) instead of crashing
        # the whole image's extraction, which is what happened before when
        # two adjacent amounts on one row collapsed into e.g. ".49046.91".
        amount_value = safe_parse_amount(amount_match.group(0))

        tx = {
            "date": current_date_header,
            "description": row_text.strip(),
            "amount": make_field(amount_value, avg_conf, threshold, extra={"currency": "PKR"}),
            "direction": direction if direction else None,
            "incomplete": is_cutoff,
        }
        if amount_value is None:
            tx["warning"] = "amount text could not be cleanly parsed (possibly merged OCR tokens): " + amount_match.group(0)
        if direction is None:
            tx["warning"] = tx.get("warning", "") + " could not determine debit/credit direction from available cues"
        if is_cutoff:
            tx["warning"] = tx.get("warning", "") + " row appears cropped at screen edge"
        transactions.append(tx)

    return transactions


def extract(engine, image_path: str, threshold: float = config.DEFAULT_CONFIDENCE_THRESHOLD) -> dict:
    tokens = engine.read(image_path)
    app = detect_app(tokens)

    image_height = None
    try:
        from PIL import Image
        with Image.open(image_path) as im:
            image_height = im.height
    except Exception:
        pass

    balance = extract_balance(tokens, threshold)
    transactions = extract_transactions(tokens, app, image_height, threshold)

    warnings = []
    if app == "unknown":
        warnings.append("Could not confidently identify wallet app (Easypaisa/JazzCash) from page text.")
    if not transactions:
        warnings.append("No transaction-shaped rows detected.")
    if not tokens:
        warnings.append("OCR engine returned zero tokens for this image.")

    return {
        "document_type": "wallet_statement",
        "provider": app,
        "processing_engine": engine.name,
        "fields": {"account_balance": balance},
        "transactions": transactions,
        "warnings": warnings,
    }
