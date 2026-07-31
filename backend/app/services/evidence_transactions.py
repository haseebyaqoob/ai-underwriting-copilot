"""
This session's core new pipeline piece: turns the raw `FieldResult`/
`ExtractedFieldResult` list a document extraction just produced (Module
4/5's output, unchanged) into normalized `EvidenceTransaction` rows.

Split deliberately into a **pure function** (`normalize_fields_to_transactions`,
no DB/ORM/session, just dataclasses in and dataclasses out) and a thin
persistence wrapper (`persist_transactions`) that takes the pure
function's output and writes it. This split exists specifically so the
normalization logic itself -- the part most likely to have edge-case
bugs in date parsing / direction inference -- can be unit-tested with
plain Python and no database, which matters a great deal in an
environment where a real Postgres instance isn't available (see the
handoff doc's testing section).

Called from `app/background/tasks.py`, once per document version, right
after that module's existing `ExtractedField` writes -- additive to the
pipeline, not a replacement.
"""
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from app.db.models.enums import DocumentType, TransactionDirection

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


@dataclass(frozen=True)
class TransactionCandidate:
    transaction_date: date | None
    amount: Decimal
    direction: TransactionDirection
    counterparty_label: str | None
    extraction_confidence: float  # 0-100


@dataclass(frozen=True)
class RawField:
    """Minimal, ORM/provider-agnostic mirror of
    document_pipeline.deterministic.common.FieldResult /
    app.services.ai.provider_base.ExtractedFieldResult -- deliberately its
    own tiny type so this module has zero import coupling to either the
    deterministic pipeline or the AI provider layer, matching the
    "provider-agnostic dataclass" pattern provider_base.py already uses."""

    field_name: str
    field_value: str
    value_type: str
    confidence: float  # 0.0-1.0, matching FieldResult/ExtractedFieldResult's own convention


def parse_flexible_date(raw: str | None) -> date | None:
    """
    Handles the two shapes this codebase's extraction actually produces:
    - deterministic wallet_statement.py's regex: "12-Mar-2024", "3/07/24"
    - Gemini's free-text date field (khata "line_N_date"), which the
      extraction prompt doesn't pin to one exact format, so this is
      intentionally forgiving: numeric-or-month-name middle segment,
      2-or-4-digit year, "-" or "/" separators.
    Returns None (never raises) on anything unparseable -- a transaction
    with an unparseable date still gets recorded (evidence coverage still
    counts it), it's just excluded from date-windowed revenue sums.
    """
    if not raw:
        return None
    raw = raw.strip()
    m = re.match(r"^(\d{1,2})[-/]([A-Za-z]{3,9}|\d{1,2})[-/](\d{2,4})$", raw)
    if not m:
        return None
    day_s, mon_s, year_s = m.groups()
    try:
        day = int(day_s)
        year = int(year_s)
        if year < 100:
            year += 2000 if year < 70 else 1900
        if mon_s.isdigit():
            month = int(mon_s)
        else:
            month = _MONTHS.get(mon_s.lower()[:4].rstrip(".")[:3] if len(mon_s) >= 3 else mon_s.lower())
            if month is None:
                month = _MONTHS.get(mon_s.lower()[:3])
        if month is None or not (1 <= month <= 12) or not (1 <= day <= 31):
            return None
        return date(year, month, day)
    except (ValueError, TypeError):
        return None


def _to_decimal(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        cleaned = raw.replace(",", "").replace("PKR", "").replace("Rs", "").replace("Rs.", "").strip()
        d = Decimal(cleaned)
        if d < 0:
            return None
        return d
    except (InvalidOperation, ValueError):
        return None


_WALLET_TXN_RE = re.compile(r"^transaction_(\d+)_(date|direction|amount)$")
_KHATA_LINE_RE = re.compile(r"^line_(\d+)_(date|description|amount)$")

_DIRECTION_MAP = {
    "credit": TransactionDirection.inflow,
    "debit": TransactionDirection.outflow,
    "inflow": TransactionDirection.inflow,
    "outflow": TransactionDirection.outflow,
}

# Confidence-band discount for khata-derived cash-sale entries, per the
# architecture spec's "khata-only entries count at 50-70% face value"
# instruction. Linearly interpolated between these two bounds using the
# model's own per-line confidence (0.0-1.0) as the interpolation factor --
# a line the model was very sure about (confidence near 1.0) is trusted
# closer to 70% of face value; a line it was barely confident about
# (confidence near 0.0) is trusted closer to 50%. This is a conservative
# starting point per the spec, not a tuned/validated figure -- flagged as
# a config candidate for Module 8, not hardcoded-forever.
_KHATA_DISCOUNT_FLOOR = 0.50
_KHATA_DISCOUNT_CEILING = 0.70


def khata_discount_factor(confidence_0_1: float) -> float:
    confidence_0_1 = max(0.0, min(1.0, confidence_0_1))
    return _KHATA_DISCOUNT_FLOOR + (confidence_0_1 * (_KHATA_DISCOUNT_CEILING - _KHATA_DISCOUNT_FLOOR))


def normalize_fields_to_transactions(
    *, document_type: DocumentType, fields: list[RawField]
) -> list[TransactionCandidate]:
    """Pure function: no DB access, no I/O. See module docstring."""
    if document_type == DocumentType.wallet_statements:
        return _normalize_wallet(fields)
    if document_type == DocumentType.khata:
        return _normalize_khata(fields)
    if document_type == DocumentType.utility_bills:
        return _normalize_utility_bill(fields)
    if document_type == DocumentType.invoice:
        return _normalize_invoice(fields)
    # tax_filing, other, cnic: no transaction-shaped data to extract.
    return []


def _group_by_index(fields: list[RawField], pattern: re.Pattern) -> dict[int, dict[str, RawField]]:
    grouped: dict[int, dict[str, RawField]] = {}
    for f in fields:
        m = pattern.match(f.field_name)
        if not m:
            continue
        idx, part = int(m.group(1)), m.group(2)
        grouped.setdefault(idx, {})[part] = f
    return grouped


def _normalize_wallet(fields: list[RawField]) -> list[TransactionCandidate]:
    grouped = _group_by_index(fields, _WALLET_TXN_RE)
    out: list[TransactionCandidate] = []
    for parts in grouped.values():
        amount_f = parts.get("amount")
        amount = _to_decimal(amount_f.field_value) if amount_f else None
        if amount is None or amount == 0:
            continue
        direction_f = parts.get("direction")
        direction = _DIRECTION_MAP.get((direction_f.field_value or "").lower()) if direction_f else None
        if direction is None:
            continue  # can't safely bucket an inflow vs outflow with unknown direction
        date_f = parts.get("date")
        tx_date = parse_flexible_date(date_f.field_value) if date_f else None
        confidence = min(f.confidence for f in parts.values()) * 100  # weakest-link confidence for the triplet
        out.append(
            TransactionCandidate(
                transaction_date=tx_date,
                amount=amount,
                direction=direction,
                counterparty_label=None,
                extraction_confidence=round(confidence, 2),
            )
        )
    return out


def _normalize_khata(fields: list[RawField]) -> list[TransactionCandidate]:
    grouped = _group_by_index(fields, _KHATA_LINE_RE)
    out: list[TransactionCandidate] = []
    for parts in grouped.values():
        amount_f = parts.get("amount")
        amount = _to_decimal(amount_f.field_value) if amount_f else None
        if amount is None or amount == 0:
            continue
        date_f = parts.get("date")
        tx_date = parse_flexible_date(date_f.field_value) if date_f else None
        desc_f = parts.get("description")
        # Khata line items are treated as cash-sale inflows per the
        # architecture spec ("khata-derived cash sales") -- a khata is a
        # daily sales ledger in this product's target segment (informal
        # retail/kiryana), not a general-purpose expense log. This is a
        # deliberate simplification flagged in the handoff doc: a khata
        # that also records outgoing payments would currently have those
        # miscounted as inflow too.
        confidence = amount_f.confidence * 100
        out.append(
            TransactionCandidate(
                transaction_date=tx_date,
                amount=amount,
                direction=TransactionDirection.inflow,
                counterparty_label=desc_f.field_value if desc_f else None,
                extraction_confidence=round(confidence, 2),
            )
        )
    return out


def _normalize_utility_bill(fields: list[RawField]) -> list[TransactionCandidate]:
    amount_f = next((f for f in fields if f.field_name in ("amount_payable", "total_amount", "bill_amount")), None)
    if amount_f is None:
        return []
    amount = _to_decimal(amount_f.field_value)
    if amount is None or amount == 0:
        return []
    date_f = next((f for f in fields if f.field_name in ("due_date", "billing_month", "bill_date")), None)
    tx_date = parse_flexible_date(date_f.field_value) if date_f else None
    return [
        TransactionCandidate(
            transaction_date=tx_date,
            amount=amount,
            direction=TransactionDirection.scale_proxy,
            counterparty_label="utility bill",
            extraction_confidence=round(amount_f.confidence * 100, 2),
        )
    ]


def persist_transactions(
    db,
    *,
    application_id,
    document_id,
    document_version_id,
    document_type: DocumentType,
    fields: list[RawField],
) -> int:
    """Thin persistence wrapper around `normalize_fields_to_transactions`.
    Called once per document version, from the Celery task, right after
    that same task's existing `ExtractedField` writes. Returns the number
    of rows written. Idempotency note: this session doesn't de-duplicate
    re-processing of the *same* document_version_id (there's no unique
    constraint on document_version_id here) -- in practice
    `process_document_task` only ever runs once per version today (no
    retry path re-invokes it per version, see tasks.py's `max_retries=0`
    docstring), so this hasn't been an issue, but a future retry/re-run
    path should delete-then-reinsert for that document_version_id rather
    than assume this. Flagged in the handoff doc.
    """
    from app.db.models.evidence_transaction import EvidenceTransaction

    candidates = normalize_fields_to_transactions(document_type=document_type, fields=fields)
    for c in candidates:
        db.add(
            EvidenceTransaction(
                application_id=application_id,
                document_id=document_id,
                document_version_id=document_version_id,
                source_type=document_type,
                transaction_date=c.transaction_date,
                amount=c.amount,
                direction=c.direction,
                counterparty_label=c.counterparty_label,
                extraction_confidence=c.extraction_confidence,
            )
        )
    return len(candidates)


def _normalize_invoice(fields: list[RawField]) -> list[TransactionCandidate]:
    """Invoice line items are a plausibility signal only (spec: "invoice-
    implied volume flag"), never summed into the revenue estimate --
    stored as `scale_proxy`, same as utility bills."""
    total_f = next((f for f in fields if f.field_name in ("invoice_total", "total_amount", "amount")), None)
    if total_f is None:
        return []
    amount = _to_decimal(total_f.field_value)
    if amount is None or amount == 0:
        return []
    date_f = next((f for f in fields if f.field_name in ("invoice_date", "date")), None)
    tx_date = parse_flexible_date(date_f.field_value) if date_f else None
    return [
        TransactionCandidate(
            transaction_date=tx_date,
            amount=amount,
            direction=TransactionDirection.scale_proxy,
            counterparty_label="invoice",
            extraction_confidence=round(total_f.confidence * 100, 2),
        )
    ]
