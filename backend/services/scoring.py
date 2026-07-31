"""
A transparent, disclosed-weight rubric -- explicitly NOT an ML model (no
training data exists yet, and explainability is core to the product
pitch; see architecture spec's "Scoring" section). Every factor is scored
independently and shown to the officer with its own explanation.

**Evidence floor is a hard rule, enforced here, not a suggestion**: if
fewer than 2 independent document types are present, OR the observed date
range is under ~2 weeks, OR the CNIC fails structural validation, this
module refuses to produce a score at all -- `compute_score` returns an
`InsufficientEvidence` result instead of a `ScoreResult`. The caller
(application_service.py) is responsible for rendering that as a real UI
state ("insufficient evidence to generate an assessment"), never as a
degraded/low score.

Gating principle: this module only ever gates whether an *assessment*
renders. It has no opinion on whether an application can be submitted --
that would exclude the thin-file/informal-borrower population this
product exists to serve, and nothing in this module is wired to block
submission.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.services.revenue_estimator import RevenueEstimate

MIN_INDEPENDENT_DOCUMENT_TYPES = 2
MIN_OBSERVED_DAYS = 14  # "~2 weeks" per spec

# Disclosed factor weights -- sum to 100. Existing-debt-exposure is
# deliberately NOT a scored factor (no eCIB integration exists yet); it's
# surfaced as an explicit "unknown -- not checked" line instead, per the
# spec's "never silently treat as zero" instruction, and does not
# contribute to or subtract from the numeric score.
_WEIGHTS = {
    "income_stability": 30,
    "evidence_coverage": 20,
    "cross_document_consistency": 20,
    "cash_flow_vs_loan_ask": 20,
    "business_tenure_scale": 10,
}

_SCORE_LOW_THRESHOLD = 720
_SCORE_MODERATE_THRESHOLD = 640


@dataclass(frozen=True)
class ScoreFactor:
    key: str
    label: str
    weight_pct: int
    factor_score_0_100: float
    explanation: str


@dataclass(frozen=True)
class DebtExposureNote:
    status: str = "unknown_not_checked"
    note: str = "Existing debt exposure: unknown — not checked (no eCIB/credit-bureau integration exists yet)."


@dataclass(frozen=True)
class ScoreResult:
    score_0_1000: int
    confidence_0_100: float
    risk_level: str  # "low" | "moderate" | "elevated"
    factors: list[ScoreFactor]
    debt_exposure: DebtExposureNote
    weeks_of_data: float


@dataclass(frozen=True)
class InsufficientEvidence:
    reasons: list[str]
    missing_document_types: list[str]
    document_types_present: list[str]
    weeks_of_data: float


def evidence_floor_check(
    *,
    document_types_present: set[str],
    weeks_of_data: float,
    cnic_digits: str | None,
    all_required_types: tuple[str, ...] = ("wallet_statements", "khata", "utility_bills"),
) -> InsufficientEvidence | None:
    """Returns None if the floor is met (safe to score); otherwise an
    `InsufficientEvidence` describing exactly why, in officer/UI-ready
    language, and which document types would help close the gap."""
    reasons: list[str] = []

    if len(document_types_present) < MIN_INDEPENDENT_DOCUMENT_TYPES:
        reasons.append(
            f"Only {len(document_types_present)} independent document type(s) present "
            f"(need at least {MIN_INDEPENDENT_DOCUMENT_TYPES})."
        )
    if weeks_of_data * 7 < MIN_OBSERVED_DAYS:
        reasons.append(
            f"Observed date range across all sources is under {MIN_OBSERVED_DAYS} days "
            f"({weeks_of_data:.1f} weeks found)."
        )
    if cnic_digits is None or len(cnic_digits) != 13 or not cnic_digits.isdigit():
        reasons.append("CNIC failed structural validation (13-digit format required).")

    if not reasons:
        return None

    missing = [t for t in all_required_types if t not in document_types_present]
    return InsufficientEvidence(
        reasons=reasons,
        missing_document_types=missing,
        document_types_present=sorted(document_types_present),
        weeks_of_data=weeks_of_data,
    )


def _income_stability_score(revenue: RevenueEstimate) -> tuple[float, str]:
    if revenue.blended_estimate_high_monthly is None or revenue.blended_estimate_high_monthly == 0:
        return 0.0, "No usable revenue data."
    low = float(revenue.blended_estimate_low_monthly or 0)
    high = float(revenue.blended_estimate_high_monthly or 0)
    spread_pct = ((high - low) / high * 100) if high else 100.0
    # Tighter spread between the verified floor and the full khata-inclusive
    # figure implies more stable/consistent income evidence, not
    # necessarily higher revenue -- level and variance both feed this,
    # per the spec's "level + variance of the revenue estimate" wording.
    variance_score = max(0.0, 100 - spread_pct)
    level_bonus = min(20.0, high / 50_000)  # soft, capped nudge for larger verified scale
    combined = min(100.0, variance_score * 0.8 + level_bonus)
    return round(combined, 1), (
        f"Blended estimate range PKR {low:,.0f}–{high:,.0f}/mo "
        f"(spread {spread_pct:.0f}%, based on {revenue.months_of_data:.1f} months of data)."
    )


def _evidence_coverage_score(document_types_present: set[str], weeks_of_data: float) -> tuple[float, str]:
    type_score = min(100.0, len(document_types_present) * 25)
    window_score = min(100.0, weeks_of_data / 12.0 * 100)  # 12 weeks (~3mo) treated as "full" coverage
    combined = round(type_score * 0.6 + window_score * 0.4, 1)
    return combined, (
        f"{len(document_types_present)} independent document type(s) over {weeks_of_data:.1f} weeks of data."
    )


def _consistency_score(consistency_pass_count: int, consistency_total: int) -> tuple[float, str]:
    if consistency_total == 0:
        return 50.0, "No consistency checks were applicable yet."
    pct = consistency_pass_count / consistency_total * 100
    return round(pct, 1), f"{consistency_pass_count}/{consistency_total} consistency checks passed."


def _cash_flow_vs_loan_score(revenue: RevenueEstimate, amount_pkr: Decimal, tenor_months: int) -> tuple[float, str]:
    monthly = float(revenue.blended_estimate_low_monthly or 0)
    if monthly <= 0 or tenor_months <= 0:
        return 0.0, "Insufficient revenue data to assess debt-service coverage."
    implied_installment = float(amount_pkr) / tenor_months
    dscr = monthly / implied_installment if implied_installment else 0.0
    # DSCR >= 2.0 is comfortably serviceable -> 100; DSCR <= 0.5 -> 0.
    # Linear in between. This is a simple, disclosed rule, not a
    # statistically-fit curve -- flagged as a Module 8 config candidate.
    score = max(0.0, min(100.0, (dscr - 0.5) / (2.0 - 0.5) * 100))
    return round(score, 1), f"Debt-service coverage ratio ≈ {dscr:.2f} (verified-floor monthly ÷ implied installment)."


def _tenure_scale_score(years_operating: int | None, has_utility_bill_scale: bool) -> tuple[float, str]:
    years = years_operating or 0
    years_score = min(100.0, years / 5.0 * 100)
    bonus = 10.0 if has_utility_bill_scale else 0.0
    combined = min(100.0, years_score * 0.9 + bonus)
    return round(combined, 1), f"{years} year(s) reported in operation" + (
        ", utility-bill scale signal present." if has_utility_bill_scale else "."
    )


def compute_score(
    *,
    revenue: RevenueEstimate,
    document_types_present: set[str],
    cnic_digits: str | None,
    consistency_pass_count: int,
    consistency_total: int,
    amount_pkr: Decimal,
    tenor_months: int,
    years_operating: int | None,
) -> ScoreResult | InsufficientEvidence:
    floor_failure = evidence_floor_check(
        document_types_present=document_types_present,
        weeks_of_data=revenue.weeks_of_data,
        cnic_digits=cnic_digits,
    )
    if floor_failure is not None:
        return floor_failure

    income_score, income_note = _income_stability_score(revenue)
    coverage_score, coverage_note = _evidence_coverage_score(document_types_present, revenue.weeks_of_data)
    consistency_score, consistency_note = _consistency_score(consistency_pass_count, consistency_total)
    dscr_score, dscr_note = _cash_flow_vs_loan_score(revenue, amount_pkr, tenor_months)
    tenure_score, tenure_note = _tenure_scale_score(years_operating, "utility_bills" in document_types_present)

    factors = [
        ScoreFactor("income_stability", "Income stability", _WEIGHTS["income_stability"], income_score, income_note),
        ScoreFactor("evidence_coverage", "Evidence strength & coverage", _WEIGHTS["evidence_coverage"], coverage_score, coverage_note),
        ScoreFactor("cross_document_consistency", "Cross-document consistency", _WEIGHTS["cross_document_consistency"], consistency_score, consistency_note),
        ScoreFactor("cash_flow_vs_loan_ask", "Cash flow vs. loan ask", _WEIGHTS["cash_flow_vs_loan_ask"], dscr_score, dscr_note),
        ScoreFactor("business_tenure_scale", "Business tenure & scale", _WEIGHTS["business_tenure_scale"], tenure_score, tenure_note),
    ]

    weighted_0_100 = sum(f.factor_score_0_100 * f.weight_pct / 100 for f in factors)
    score_0_1000 = round(weighted_0_100 * 10)

    risk_level = (
        "low" if score_0_1000 > _SCORE_LOW_THRESHOLD
        else "moderate" if score_0_1000 > _SCORE_MODERATE_THRESHOLD
        else "elevated"
    )

    # Confidence in the score itself (distinct from the score) is reduced
    # by thin data, per the spec's "sparse history reduces score
    # *confidence*, not the score itself" instruction -- weeks_of_data
    # below ~8 weeks (2 months) linearly reduces confidence down to a 50%
    # floor rather than ever hitting 0 (0 would imply "we know nothing",
    # but the evidence floor already guarantees a minimum baseline before
    # we get here at all).
    confidence = 50.0 + min(50.0, revenue.weeks_of_data / 8.0 * 50.0)

    return ScoreResult(
        score_0_1000=max(0, min(1000, score_0_1000)),
        confidence_0_100=round(confidence, 1),
        risk_level=risk_level,
        factors=factors,
        debt_exposure=DebtExposureNote(),
        weeks_of_data=revenue.weeks_of_data,
    )
