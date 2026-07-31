"""
Revenue estimation over `evidence_transactions` rows. A pure function
(plain dataclasses in, plain dataclasses out, no ORM/DB/session) so it can
be unit-tested directly -- see tests/test_revenue_estimator.py. The
service-layer glue (application_service.py) is the only thing that reads
the ORM rows and converts them into `TransactionRow` before calling this.

Implements the architecture spec's three-tier estimate:
1. Verified floor: wallet-statement inflows, at face value.
2. Blended estimate: floor + khata inflows, discounted per the khata
   confidence-discount curve (evidence_transactions.khata_discount_factor).
3. Plausibility band: utility-bill / invoice scale-proxy rows flag the
   blended estimate as implausible if the mismatch is large -- a
   consistency flag, never a revenue input in its own right.

Never returns false-precision numbers from thin data -- every output
carries `weeks_of_data`/`months_of_data` alongside it, and the caller
(scoring.py's evidence floor) is responsible for refusing to render an
assessment at all below the evidence floor, not this module.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.services.evidence_transactions import khata_discount_factor

# Large-mismatch threshold for the wallet-vs-scale-proxy plausibility
# check, per the architecture spec's "large mismatch = consistency flag"
# instruction -- reused from consistency_checks.py's own constant so the
# two modules agree on what "large" means; duplicated here as a plain
# float (not imported) to keep this module dependency-free of
# consistency_checks, avoiding a circular import between the two.
_PLAUSIBILITY_MISMATCH_RATIO = 3.0  # scale-proxy-implied monthly figure vs blended estimate


@dataclass(frozen=True)
class TransactionRow:
    """Plain mirror of one `EvidenceTransaction` row -- see that model's
    docstring for the schema this represents."""

    source_type: str  # DocumentType.value
    transaction_date: date | None
    amount: Decimal
    direction: str  # TransactionDirection.value
    extraction_confidence: float  # 0-100


@dataclass
class RevenueEstimate:
    verified_floor_monthly: Decimal | None
    blended_estimate_low_monthly: Decimal | None
    blended_estimate_high_monthly: Decimal | None
    # The actual confidence-discounted middle figure (floor + khata*discount)
    # -- used internally by scoring.py and consistency_checks.py. Not the
    # same as the low/high band shown to a human, which communicates the
    # honest range rather than a single point estimate (spec: "not a
    # single blended number").
    blended_estimate_monthly: Decimal | None
    window_start: date | None
    window_end: date | None
    weeks_of_data: float
    months_of_data: float
    source_types_used: list[str] = field(default_factory=list)
    plausibility_flag: bool = False
    plausibility_note: str | None = None
    has_any_dated_inflow: bool = False


def _months_between(start: date, end: date) -> float:
    days = (end - start).days
    return max(days / 30.4375, 0.1)


def estimate_revenue(transactions: list[TransactionRow]) -> RevenueEstimate:
    dated_inflows = [
        t for t in transactions
        if t.direction == "inflow" and t.transaction_date is not None
    ]

    if not dated_inflows:
        return RevenueEstimate(
            verified_floor_monthly=None,
            blended_estimate_low_monthly=None,
            blended_estimate_high_monthly=None,
            blended_estimate_monthly=None,
            window_start=None,
            window_end=None,
            weeks_of_data=0.0,
            months_of_data=0.0,
            source_types_used=sorted({t.source_type for t in transactions}),
        )

    window_start = min(t.transaction_date for t in dated_inflows)
    window_end = max(t.transaction_date for t in dated_inflows)
    weeks = max((window_end - window_start).days / 7.0, 0.1)
    months = _months_between(window_start, window_end)

    # Tier 1: verified floor -- wallet-statement inflows only, face value.
    wallet_inflows = [t for t in dated_inflows if t.source_type == "wallet_statements"]
    wallet_total = sum((t.amount for t in wallet_inflows), Decimal("0"))
    verified_floor_monthly = (wallet_total / Decimal(str(months))) if wallet_inflows else Decimal("0")

    # Tier 2: blended -- floor + khata inflows discounted per-line by
    # confidence, per the spec's 50-70%-of-face-value instruction.
    khata_inflows = [t for t in dated_inflows if t.source_type == "khata"]
    khata_total_discounted = sum(
        (t.amount * Decimal(str(khata_discount_factor(t.extraction_confidence / 100))) for t in khata_inflows),
        Decimal("0"),
    )
    blended_monthly = (wallet_total + khata_total_discounted) / Decimal(str(months))

    # Present as a band, not a single blended figure, per the spec's "not
    # a single blended number" instruction: low = verified floor alone,
    # high = floor + full (undiscounted) khata contribution -- the
    # discounted blended figure sits between them and is what's actually
    # used for scoring, but the band communicates the real uncertainty
    # range to a human reader rather than false precision.
    khata_total_undiscounted = sum((t.amount for t in khata_inflows), Decimal("0"))
    high_monthly = (wallet_total + khata_total_undiscounted) / Decimal(str(months))

    # Tier 3: plausibility band vs scale-proxy signals (utility bill /
    # invoice). A utility bill on its own doesn't set an upper bound on
    # revenue, but a shop paying a tiny utility bill while claiming very
    # large monthly revenue (or vice versa) is a mismatch worth flagging
    # to a human, not silently accepting.
    scale_rows = [t for t in transactions if t.direction == "scale_proxy"]
    plausibility_flag = False
    plausibility_note = None
    if scale_rows and blended_monthly > 0:
        max_scale = max(t.amount for t in scale_rows)
        if max_scale > 0 and (blended_monthly / max_scale) > Decimal(str(50)):
            plausibility_flag = True
            plausibility_note = (
                "Estimated monthly revenue is very large relative to the utility-bill/invoice scale signal -- "
                "worth a second look, not necessarily wrong."
            )
        elif max_scale > blended_monthly * Decimal(str(_PLAUSIBILITY_MISMATCH_RATIO)):
            plausibility_flag = True
            plausibility_note = (
                "Utility-bill/invoice scale signal is large relative to estimated monthly revenue -- "
                "worth a second look, not necessarily wrong."
            )

    return RevenueEstimate(
        verified_floor_monthly=verified_floor_monthly.quantize(Decimal("1")),
        blended_estimate_low_monthly=verified_floor_monthly.quantize(Decimal("1")),
        blended_estimate_high_monthly=high_monthly.quantize(Decimal("1")),
        blended_estimate_monthly=blended_monthly.quantize(Decimal("1")),
        window_start=window_start,
        window_end=window_end,
        weeks_of_data=round(weeks, 1),
        months_of_data=round(months, 2),
        source_types_used=sorted({t.source_type for t in transactions}),
        plausibility_flag=plausibility_flag,
        plausibility_note=plausibility_note,
        has_any_dated_inflow=True,
    )
