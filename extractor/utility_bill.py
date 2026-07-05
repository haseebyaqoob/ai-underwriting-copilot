
from __future__ import annotations
import re
from html.parser import HTMLParser
import config
from utils import (fuzzy_label_match, find_nearest_value, make_field,
                    region_looks_redacted, safe_parse_amount, bbox_distance)

# Generic, config-independent shape patterns for the raw candidate scan.
# Deliberately broad — this is meant to catch every plausible date/amount on
# the page, not just the ones matching a specific canonical field's stricter
# pattern from config.py.
_MONTH_NAMES = (r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
                r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?")
_DATE_SHAPE_RE = re.compile(
    r"\b\d{1,2}[-/](?:" + _MONTH_NAMES + r")[-/]\d{2,4}\b"          # 24-Jun-2024
    r"|\b\d{4}-\d{2}-\d{2}\b"                                        # 2024-06-24
    r"|\b\d{1,2}(?:st|nd|rd|th)?\s+(?:" + _MONTH_NAMES + r")\s+\d{2,4}\b"  # 8th July 2024
    r"|\b(?:" + _MONTH_NAMES + r")[-/ ]\d{2,4}\b",                    # Jun-2024, June 2024
    re.IGNORECASE,
)
# Units/quantity numbers (e.g. "679 Units") are plain integers with no comma
# grouping or decimal point — a currency amount pattern won't catch these.
# Matched as a same-line phrase (number + "Units"/"kWh"/etc keyword) rather
# than as isolated adjacent tokens, since OCR token boundaries around a
# number-then-word pair are unreliable (sometimes merged, sometimes split).
_AMOUNT_SHAPE_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{2}\b")
_UNITS_IN_LINE_RE = re.compile(r"\b(\d{2,6})\s*(?:units?|kwh)\b", re.IGNORECASE)
# Real K-Electric/utility account numbers are long digit-only strings (often
# printed right next to or inside a barcode). Constraining to digits-only
# is what filters out barcode-graphic OCR misreads like "ETEOZU" or
# "-C1200" — those aren't shaped like a real account number at all.
_ACCOUNT_NUMBER_RE = re.compile(r"\b\d{7,15}\b")


def detect_provider(tokens) -> str:
    full_text = " ".join(t.text.lower() for t in tokens)
    for provider, keywords in config.PROVIDER_DETECTION_KEYWORDS.items():
        if any(kw in full_text for kw in keywords):
            return provider
    return "unknown"


def _group_tokens_into_lines(tokens, y_tol: float = 10.0):
    """Group tokens into visual lines by y-center proximity, sorted
    left-to-right, so a date/label spanning multiple OCR word-tokens (e.g.
    "8th" "July" "2024" as three separate tokens) can be matched as one
    string instead of being invisible to a single-token regex scan."""
    if not tokens:
        return []
    sorted_toks = sorted(tokens, key=lambda t: ((t.bbox[1] + t.bbox[3]) / 2, t.bbox[0]))
    lines, current, current_y = [], [], None
    for tok in sorted_toks:
        yc = (tok.bbox[1] + tok.bbox[3]) / 2
        if current_y is None or abs(yc - current_y) <= y_tol:
            current.append(tok)
            current_y = yc if current_y is None else (current_y + yc) / 2
        else:
            lines.append(current)
            current = [tok]
            current_y = yc
    if current:
        lines.append(current)
    return lines


def extract_scalar_fields(tokens, image_path: str, threshold: float,
                           raw_amounts: list, raw_units: list, raw_dates: list) -> dict:
    fields = {}
    used_label_bboxes = set()
def extract_scalar_fields(tokens, image_path: str, threshold: float,
                           raw_amounts: list, raw_units: list, raw_dates: list,
                           raw_account_numbers: list) -> dict:
    fields = {}
    used_label_bboxes = set()
    used_value_bboxes = set()  # prevents one value token being claimed by
                                # more than one canonical field.

    for canonical, aliases in config.UTILITY_BILL_FIELD_ALIASES.items():
        if canonical in ("billing_history", "payment_history"):
            continue  # handled as tables, not scalar fields

        # amount_payable, current_units, last_month_units, due_date,
        # issue_date, account_number: source from the raw scan, which
        # proved more reliable than the old bbox-nearest-neighbor approach
        # below (it correctly finds e.g. "Rs.42,719" tagged next to
        # "Amount Payable" where the old path picked an unrelated small
        # number). issue_date and last_month_units reuse the SAME raw pools
        # as due_date/current_units — the data was already being found at
        # high confidence, it just had no canonical field to land in yet.
        if canonical == "amount_payable":
            fields[canonical] = _pick_from_raw_candidates(
                raw_amounts, aliases, threshold, currency="PKR")
            continue
        if canonical in ("current_units", "last_month_units"):
            fields[canonical] = _pick_from_raw_candidates(
                raw_units, aliases, threshold, currency=None)
            continue
        if canonical in ("due_date", "issue_date"):
            # allow_unmatched_fallback=False: a confidently-wrong date is
            # worse than an honest "not found" for underwriting — see
            # _pick_from_raw_candidates docstring.
            fields[canonical] = _pick_from_raw_candidates(
                raw_dates, aliases, threshold, currency=None,
                allow_unmatched_fallback=False)
            continue
        if canonical == "account_number":
            # Digit-only shape filters out barcode-graphic OCR misreads
            # (e.g. "ETEOZU", "-C1200") that the old free-text nearest-value
            # path was picking up — those aren't shaped like a real account
            # number at all, they're letters, which real account numbers
            # on these bills never contain.
            fields[canonical] = _pick_from_raw_candidates(
                raw_account_numbers, aliases, threshold, currency=None,
                allow_unmatched_fallback=False)
            continue
        if canonical == "customer_name":
            # Commercial/business-account bills (e.g. "M/S FALAK NAZ PLAZA")
            # often print the account holder's name as a plain addressee
            # line with NO explicit "Customer Name:" label anywhere nearby —
            # the label-anchored strategy below has nothing to anchor on in
            # that case. Check for the standard "M/S" business-name prefix
            # first; only fall through to label search if that's absent.
            ms_name = _extract_ms_prefixed_name(tokens)
            if ms_name is not None:
                fields[canonical] = make_field(ms_name.text.strip(), ms_name.confidence, threshold,
                                                extra={"reason": "matched 'M/S' business-account name prefix, no explicit label needed"})
                continue
            # else fall through to the generic label-based search below

        pattern = config.UTILITY_BILL_VALUE_PATTERNS.get(canonical, r".+")
        label_token = None
        for tok in tokens:
            if fuzzy_label_match(tok.text, aliases):
                label_token = tok
                break

        if label_token is None:
            fields[canonical] = make_field(None, 0.0, threshold,
                                            extra={"reason": "label not found"})
            continue

        used_label_bboxes.add(label_token.bbox)
        exclude = used_label_bboxes | used_value_bboxes
        value_tok = find_nearest_value(label_token.bbox, tokens, pattern,
                                        exclude_bboxes=exclude)

        if value_tok is None:
            if region_looks_redacted(image_path, label_token.bbox):
                fields[canonical] = make_field(None, 0.0, threshold,
                                                extra={"reason": "possibly redacted"})
            else:
                fields[canonical] = make_field(None, 0.0, threshold,
                                                extra={"reason": "value not found near label"})
            continue

        used_value_bboxes.add(value_tok.bbox)
        fields[canonical] = make_field(value_tok.text.strip(), value_tok.confidence, threshold)

    return fields


def _extract_ms_prefixed_name(tokens):
    """Standard Pakistani business-bill convention: the account holder's
    name is printed as a plain addressee line starting with "M/S" (Messrs),
    with no separate "Customer Name:" label anywhere nearby. Scans grouped
    lines (not individual tokens, since OCR usually splits "M/S" from the
    business name that follows it) for this prefix. Returns a lightweight
    object with .text/.confidence, or None if not found."""
    for line in _group_tokens_into_lines(tokens):
        line_text = " ".join(t.text for t in line).strip()
        # Tolerant of common OCR misreads of "M/S" (M/S., MIS, M1S, M/s).
        if re.match(r"^M[/1I][Ss][.,]?\s+\S", line_text):
            avg_conf = sum(t.confidence for t in line) / len(line)
            return type("_Cand", (), {"text": line_text, "confidence": avg_conf})()
    return None


def _pick_from_raw_candidates(candidates: list, aliases: list[str],
                               threshold: float, currency: str | None,
                               allow_unmatched_fallback: bool = True) -> dict:
    """Pick the best raw-scan candidate whose nearby_text fuzzy-matches one
    of this field's label aliases.

    allow_unmatched_fallback controls what happens when NO candidate has a
    matching nearby label: True falls back to the highest-confidence
    candidate overall (reasonable for amount/units, where being roughly
    right is usually safe); False returns an honest "not found" instead
    (used for due_date) — for an underwriting pipeline, a confident-looking
    wrong date is worse than admitting the value wasn't found, since a wrong
    guess can silently pass review while a flagged null gets checked.
    """
    matched = [c for c in candidates if c.get("nearby_text")
               and fuzzy_label_match(c["nearby_text"], aliases)]

    if not matched and not allow_unmatched_fallback:
        return make_field(None, 0.0, threshold,
                           extra={"reason": "no candidate on page had a nearby label matching "
                                            "this field — see raw candidates list instead of guessing"})

    pool = matched if matched else candidates
    if not pool:
        return make_field(None, 0.0, threshold, extra={"reason": "no candidate value found on page"})

    best = max(pool, key=lambda c: c["confidence"])
    value = best.get("parsed_value", best["text"])
    extra = {}
    if currency:
        extra["currency"] = currency
    if not matched:
        extra["reason"] = "no candidate had a matching nearby label — picked highest-confidence value on page"
    return make_field(value, best["confidence"], threshold, extra=extra)


def extract_raw_candidates(tokens, max_label_distance: float = 200) -> dict:
    """Comprehensive, non-committal scan: every date-shaped, amount-shaped,
    units-shaped, and account-number-shaped token (or same-line group of
    tokens) on the page, each with its own confidence/bbox and the text of
    the nearest other token (a plausible label), so both our own
    field-picking and a downstream LLM can resolve ambiguity using full
    page context instead of one brittle guess.
    """
    dates, amounts, units, account_numbers = [], [], [], []
    seen_date_texts = set()

    # Pass 1: individual tokens (catches single-token dates/amounts/IDs).
    for tok in tokens:
        text = tok.text.strip()
        if not text:
            continue
        if _DATE_SHAPE_RE.search(text) and text not in seen_date_texts:
            seen_date_texts.add(text)
            dates.append({
                "text": text,
                "confidence": round(float(tok.confidence), 4),
                "bbox": list(tok.bbox),
                "nearby_text": _nearest_other_token_text(tok, tokens, max_label_distance),
            })
        if _AMOUNT_SHAPE_RE.search(text):
            amounts.append({
                "text": text,
                "parsed_value": safe_parse_amount(text),
                "confidence": round(float(tok.confidence), 4),
                "bbox": list(tok.bbox),
                "nearby_text": _nearest_other_token_text(tok, tokens, max_label_distance),
            })
        # Account numbers: digit-only shape, deliberately excludes anything
        # with letters mixed in — real account numbers on these bills are
        # pure digit strings; alphanumeric garbage near the label is far
        # more likely a misread of the adjacent barcode graphic than a
        # real account number with letters in it.
        if _ACCOUNT_NUMBER_RE.fullmatch(text):
            account_numbers.append({
                "text": text,
                "confidence": round(float(tok.confidence), 4),
                "bbox": list(tok.bbox),
                "nearby_text": _nearest_other_token_text(tok, tokens, max_label_distance),
            })

    # Pass 2: same-line phrases — multi-token dates (e.g. "8th" "July"
    # "2024" as three separate OCR tokens) and units-with-keyword (e.g.
    # "679" "Units" as two tokens) both need this, since OCR token
    # boundaries around such pairs are unreliable (sometimes merged into
    # one token, sometimes split into two).
    for line in _group_tokens_into_lines(tokens):
        line_text = " ".join(t.text for t in line).strip()
        if not line_text:
            continue

        if line_text not in seen_date_texts:
            m = _DATE_SHAPE_RE.search(line_text)
            if m and m.group(0) not in seen_date_texts:
                matched_text = m.group(0)
                seen_date_texts.add(matched_text)
                avg_conf = sum(t.confidence for t in line) / len(line)
                union_bbox = [
                    min(t.bbox[0] for t in line), min(t.bbox[1] for t in line),
                    max(t.bbox[2] for t in line), max(t.bbox[3] for t in line),
                ]
                line_bboxes = {t.bbox for t in line}
                other_tokens = [t for t in tokens if t.bbox not in line_bboxes]
                nearby = _nearest_other_token_text(line[0], other_tokens, max_label_distance)
                dates.append({
                    "text": matched_text,
                    "confidence": round(float(avg_conf), 4),
                    "bbox": union_bbox,
                    "nearby_text": nearby,
                    "note": "matched across multiple OCR tokens on the same line",
                })

        um = _UNITS_IN_LINE_RE.search(line_text)
        if um:
            avg_conf = sum(t.confidence for t in line) / len(line)
            union_bbox = [
                min(t.bbox[0] for t in line), min(t.bbox[1] for t in line),
                max(t.bbox[2] for t in line), max(t.bbox[3] for t in line),
            ]
            line_bboxes = {t.bbox for t in line}
            other_tokens = [t for t in tokens if t.bbox not in line_bboxes]
            nearby = _nearest_other_token_text(line[0], other_tokens, max_label_distance)
            units.append({
                "text": um.group(0),
                "parsed_value": safe_parse_amount(um.group(1)),
                "confidence": round(float(avg_conf), 4),
                "bbox": union_bbox,
                "nearby_text": nearby,
                "note": "matched as number+units phrase on the same line",
            })

    return {
        "raw_dates_detected": dates,
        "raw_amounts_detected": amounts,
        "raw_units_detected": units,
        "raw_account_numbers_detected": account_numbers,
    }


def _nearest_other_token_text(token, tokens, max_distance: float) -> str | None:
    best, best_dist = None, float("inf")
    for other in tokens:
        if other.bbox == token.bbox:
            continue
        d = bbox_distance(token.bbox, other.bbox)
        if d < best_dist and d <= max_distance:
            best_dist = d
            best = other
    return best.text.strip() if best else None


class _SimpleTableHTMLParser(HTMLParser):
    """Minimal <table><tr><td>/<th> parser — PP-StructureV3's pred_html output
    is simple, single-level table markup, so a lightweight stdlib parser is
    enough; no need for a heavier HTML library dependency."""
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._current_row = []
        elif tag in ("td", "th"):
            self._current_cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._current_cell is not None:
            if self._current_row is not None:
                self._current_row.append("".join(self._current_cell).strip())
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None

    def handle_data(self, data):
        if self._current_cell is not None:
            self._current_cell.append(data)


def parse_html_table(html: str) -> list[list[str]]:
    """Parse a simple HTML table string into rows of cell strings. Returns
    [] on any parse failure rather than raising — a malformed table shouldn't
    crash the whole image's extraction."""
    if not html:
        return []
    try:
        parser = _SimpleTableHTMLParser()
        parser.feed(html)
        return parser.rows
    except Exception:
        return []


def _looks_like_header_row(cells: list[str]) -> bool:
    """Heuristic: a header row is mostly non-numeric text (column labels
    like 'MM/YY', 'Billed Amount'), whereas a data row is mostly numeric/
    date-shaped. Used to skip the header rather than parsing it as data."""
    numeric_like = sum(1 for c in cells if re.search(r"\d", c))
    return numeric_like <= len(cells) / 2


def extract_tables(engine, image_path: str, threshold: float) -> dict:
    """Preserve billing_history / payment_history as arrays of typed rows,
    using the engine's native table output rather than re-parsing flat text.

    On these K-Electric bills, "Billing & Payment History" is ONE physical
    table with four columns — MM/YY, Billed Amount, Pay-Date, Payment — not
    two separate tables. Each row is split into a billing_history entry
    (month + billed_amount) and a payment_history entry (pay_date +
    payment) from the same row, rather than assuming the engine returns two
    separate table blocks.

    Honesty note: engine.read_tables() only returns HTML structure, not
    per-cell confidence scores (those are only available from .read()'s
    token-level output) — so these rows are marked flagged=True with an
    explicit reason rather than being given a fabricated confidence number.
    """
    tables_out = {"billing_history": [], "payment_history": []}
    try:
        raw_tables = engine.read_tables(image_path)
    except Exception:
        raw_tables = []

    if not raw_tables:
        return tables_out

    for raw_html in raw_tables:
        rows = parse_html_table(raw_html)
        if not rows:
            continue
        for cells in rows:
            if _looks_like_header_row(cells):
                continue  # skip column-label row, not a data row
            if len(cells) < 4:
                # Unexpected shape — don't guess a column mapping, surface
                # the raw cells instead so nothing is silently dropped.
                tables_out["billing_history"].append({
                    "month": None, "billed_amount": None,
                    "confidence": 0.0, "flagged": True,
                    "reason": f"row had {len(cells)} cell(s), expected 4 (MM/YY, "
                              f"Billed Amount, Pay-Date, Payment) — see raw_cells",
                    "raw_cells": cells,
                })
                continue

            month, billed_amount_text, pay_date, payment_text = cells[0], cells[1], cells[2], cells[3]
            tables_out["billing_history"].append({
                "month": month.strip() or None,
                "billed_amount": safe_parse_amount(billed_amount_text),
                "confidence": 0.0,
                "flagged": True,
                "reason": "cell-level confidence not available from this engine call — verify against source image",
            })
            tables_out["payment_history"].append({
                "pay_date": pay_date.strip() or None,
                "payment": safe_parse_amount(payment_text),
                "confidence": 0.0,
                "flagged": True,
                "reason": "cell-level confidence not available from this engine call — verify against source image",
            })

    return tables_out


def extract(engine, image_path: str, threshold: float = config.DEFAULT_CONFIDENCE_THRESHOLD) -> dict:
    tokens = engine.read(image_path)
    provider = detect_provider(tokens)
    raw_candidates = extract_raw_candidates(tokens)
    fields = extract_scalar_fields(tokens, image_path, threshold,
                                    raw_candidates["raw_amounts_detected"],
                                    raw_candidates["raw_units_detected"],
                                    raw_candidates["raw_dates_detected"],
                                    raw_candidates["raw_account_numbers_detected"])
    tables = extract_tables(engine, image_path, threshold)

    warnings = []
    if provider == "unknown":
        warnings.append("Could not confidently identify utility provider from page text.")
    if not tokens:
        warnings.append("OCR engine returned zero tokens for this image.")
    if len(raw_candidates["raw_dates_detected"]) > 1:
        warnings.append(
            "Multiple dates detected on page — 'due_date' field is a best-effort "
            "single guess; see raw_dates_detected for all candidates with context."
        )

    return {
        "document_type": "utility_bill",
        "provider": provider,
        "processing_engine": engine.name,
        "fields": fields,
        "raw_dates_detected": raw_candidates["raw_dates_detected"],
        "raw_amounts_detected": raw_candidates["raw_amounts_detected"],
        "raw_account_numbers_detected": raw_candidates["raw_account_numbers_detected"],
        "tables": tables,
        "warnings": warnings,
    }
