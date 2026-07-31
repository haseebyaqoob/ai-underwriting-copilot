"""
Cheap, arithmetic/fuzzy-match consistency checks over data the pipeline
already extracts -- no new extraction, no new Gemini calls. Pure
functions, unit-tested directly (see tests/test_consistency_checks.py).

Messaging split (architecture spec, "Consistency checks" section):
applicant-facing copy is always the same generic, non-accusatory string
regardless of which check failed; officer-facing copy is specific. This
module only computes *which checks passed/failed and why* --
`applicant_message`/`officer_message` on `ConsistencyResult` are exactly
the strings each audience is allowed to see; nothing else in the system
should reconstruct or paraphrase the officer-facing detail for an
applicant-facing surface.
"""
from dataclasses import dataclass

from rapidfuzz import fuzz

_CNIC_APPLICANT_MSG = (
    "We couldn't fully confirm this — please upload a clearer photo or an alternative document."
)

_NAME_FUZZY_MATCH_THRESHOLD = 72.0  # rapidfuzz token_sort_ratio (0-100); below this counts as a mismatch
_WALLET_VS_ESTIMATE_MISMATCH_PCT = 50.0  # spec: "flag if off by a large margin, e.g. >50%"


@dataclass(frozen=True)
class ConsistencyResult:
    check_id: str
    passed: bool
    officer_message: str
    applicant_message: str | None  # None when passed -- nothing to tell the applicant when a check is clean


def check_cnic_format(cnic_digits: str | None) -> ConsistencyResult:
    """13-digit structural validation. Schema-level validation
    (schemas/application.py's `_normalize_cnic`) already rejects a
    malformed CNIC at submission time, so in practice this should always
    pass for any CNIC that made it into the DB -- but the evidence floor
    (scoring.py) re-checks it independently rather than trusting that
    invariant blindly, since a future code path (bulk import, admin edit)
    could bypass the Pydantic validator."""
    if cnic_digits is None:
        return ConsistencyResult(
            check_id="cnic_format",
            passed=False,
            officer_message="No CNIC on file for this application.",
            applicant_message=_CNIC_APPLICANT_MSG,
        )
    if len(cnic_digits) == 13 and cnic_digits.isdigit():
        return ConsistencyResult(check_id="cnic_format", passed=True, officer_message="CNIC format valid.", applicant_message=None)
    return ConsistencyResult(
        check_id="cnic_format",
        passed=False,
        officer_message=f"CNIC failed structural validation (expected 13 digits, got {cnic_digits!r}).",
        applicant_message=_CNIC_APPLICANT_MSG,
    )


def fuzzy_name_match(name_a: str | None, name_b: str | None) -> float:
    """0-100. `token_sort_ratio` (not a raw ratio) so word order and minor
    transliteration differences ("Muhammad Adnan" vs "Adnan Muhammad", or
    OCR dropping a middle name) don't automatically read as a mismatch."""
    if not name_a or not name_b:
        return 0.0
    return fuzz.token_sort_ratio(name_a.lower().strip(), name_b.lower().strip())


def check_name_consistency(*, declared_name: str | None, other_source_label: str, other_name: str | None) -> ConsistencyResult:
    if not other_name:
        return ConsistencyResult(
            check_id=f"name_match_{other_source_label}",
            passed=True,  # nothing to compare against yet isn't a failure, just not-yet-checkable
            officer_message=f"{other_source_label}: no name available to cross-check yet.",
            applicant_message=None,
        )
    score = fuzzy_name_match(declared_name, other_name)
    if score >= _NAME_FUZZY_MATCH_THRESHOLD:
        return ConsistencyResult(
            check_id=f"name_match_{other_source_label}",
            passed=True,
            officer_message=f"{other_source_label}: name matches declared applicant name (similarity {score:.0f}).",
            applicant_message=None,
        )
    return ConsistencyResult(
        check_id=f"name_match_{other_source_label}",
        passed=False,
        officer_message=(
            f"{other_source_label}: account holder name does not match declared applicant/CNIC name "
            f"(similarity {score:.0f}, confidence: {'medium' if score >= 50 else 'low'})."
        ),
        applicant_message=_CNIC_APPLICANT_MSG,
    )


def check_wallet_vs_estimate(*, wallet_inflow_monthly, blended_estimate_monthly) -> ConsistencyResult:
    """Sanity check: does the wallet-verified floor roughly line up with
    the blended estimate, or is something off by a large margin? A large
    gap usually means either the khata is wildly inconsistent with real
    wallet activity, or the two sources cover different time windows --
    either way, worth flagging to the officer, never silently averaged
    away."""
    if wallet_inflow_monthly is None or blended_estimate_monthly is None or blended_estimate_monthly == 0:
        return ConsistencyResult(
            check_id="wallet_vs_estimate",
            passed=True,
            officer_message="Not enough data yet to compare wallet inflow against the blended estimate.",
            applicant_message=None,
        )
    diff_pct = abs(float(blended_estimate_monthly) - float(wallet_inflow_monthly)) / float(blended_estimate_monthly) * 100
    if diff_pct <= _WALLET_VS_ESTIMATE_MISMATCH_PCT:
        return ConsistencyResult(
            check_id="wallet_vs_estimate",
            passed=True,
            officer_message=f"Wallet inflow is within {diff_pct:.0f}% of the blended estimate.",
            applicant_message=None,
        )
    return ConsistencyResult(
        check_id="wallet_vs_estimate",
        passed=False,
        officer_message=(
            f"Wallet inflow differs from the blended revenue estimate by {diff_pct:.0f}% "
            f"(threshold: {_WALLET_VS_ESTIMATE_MISMATCH_PCT:.0f}%) -- confidence: medium."
        ),
        applicant_message=_CNIC_APPLICANT_MSG,
    )
