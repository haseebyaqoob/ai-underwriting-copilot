"""
Evidence Checklist catalog -- the single source of truth for what shows up
on the applicant Evidence page and Evidence Wallet.

Design note (read before adding a subtype): each checklist "subtype" is a
UI/UX-level granularity (e.g. "Easypaisa Statement", "Electricity Bill")
that maps onto ONE of the pre-existing, scoring-pipeline-facing
`DocumentType` values (khata/utility_bills/wallet_statements/tax_filing/
invoice/cnic/other) via `document_type`. Several subtypes can and do map
to the same coarse `DocumentType` -- e.g. "electricity_bill", "gas_bill",
"water_bill", and "internet_bill" all map to `DocumentType.utility_bills`,
so they all get the SAME deterministic-parser-first routing in
document_pipeline/router.py and the SAME `evidence_transactions` scale-
proxy treatment, with zero changes to scoring.py, revenue_estimator.py,
consistency_checks.py, or the deterministic parsers themselves. This is a
deliberate "preserve existing architecture" choice per the brief: the
checklist is a presentation layer on top of the existing coarse-grained
extraction/scoring pipeline, not a parallel pipeline.

`subtype` is stored as a plain string on `documents.subtype` (see the
evidence-checklist migration) for the same "avoid a Postgres native ENUM
that needs `ALTER TYPE ADD VALUE` per addition" reasoning as
`EvidenceQualityStatus` in db/models/enums.py -- the checklist is expected
to grow (new utility providers, new wallet apps) faster than the
extraction pipeline's own types.
"""
from dataclasses import dataclass
from typing import Literal

from app.db.models.enums import DocumentType

EVIDENCE_CATEGORIES: dict[str, str] = {
    "identity": "Identity",
    "business_financial": "Business Financial Records",
    "digital_transactions": "Digital Transactions",
    "business_proof": "Business Proof",
    "business_photos": "Business Photos",
    "additional": "Additional Evidence",
}

# Order categories should render in on the checklist page.
EVIDENCE_CATEGORY_ORDER: list[str] = list(EVIDENCE_CATEGORIES.keys())

# Priority tier shown on the Evidence page ("Required" / "Recommended" /
# "Optional" groupings within a category) -- see the Evidence redesign
# brief's "clearly communicate priority" requirement. A three-way tier,
# not just the pre-existing `required: bool`, which collapsed "strongly
# helps the assessment" (khata, wallet statements...) and "nice to have"
# (inventory photos...) into one bucket. `required` is kept as a derived
# property so nothing that already reads `.required` breaks.
EvidenceTier = Literal["required", "recommended", "optional"]


@dataclass(frozen=True)
class EvidenceSubtype:
    key: str
    label: str
    category: str
    document_type: DocumentType
    tier: EvidenceTier
    allow_multiple: bool
    helper_text: str = ""

    @property
    def required(self) -> bool:
        return self.tier == "required"


EVIDENCE_SUBTYPES: dict[str, EvidenceSubtype] = {
    s.key: s
    for s in [
        # -------------------------------------------------- identity
        EvidenceSubtype(
            key="cnic_front",
            label="CNIC Front",
            category="identity",
            document_type=DocumentType.cnic,
            tier="required",
            allow_multiple=False,
            helper_text="Clear photo of the front of your CNIC, all four corners visible.",
        ),
        EvidenceSubtype(
            key="cnic_back",
            label="CNIC Back",
            category="identity",
            document_type=DocumentType.cnic,
            tier="required",
            allow_multiple=False,
            helper_text="Clear photo of the back of your CNIC.",
        ),
        # -------------------------------------------- business financial
        EvidenceSubtype(
            key="khata",
            label="Khata",
            category="business_financial",
            document_type=DocumentType.khata,
            tier="recommended",
            allow_multiple=True,
        ),
        EvidenceSubtype(
            key="ledger",
            label="Ledger",
            category="business_financial",
            document_type=DocumentType.khata,
            tier="recommended",
            allow_multiple=True,
        ),
        EvidenceSubtype(
            key="cash_register",
            label="Cash Register Record",
            category="business_financial",
            document_type=DocumentType.khata,
            tier="optional",
            allow_multiple=True,
        ),
        EvidenceSubtype(
            key="sales_notebook",
            label="Sales Notebook",
            category="business_financial",
            document_type=DocumentType.khata,
            tier="optional",
            allow_multiple=True,
        ),
        EvidenceSubtype(
            key="invoices",
            label="Invoices",
            category="business_financial",
            document_type=DocumentType.invoice,
            tier="recommended",
            allow_multiple=True,
        ),
        EvidenceSubtype(
            key="receipts",
            label="Receipts",
            category="business_financial",
            document_type=DocumentType.invoice,
            tier="optional",
            allow_multiple=True,
        ),
        # ------------------------------------------- digital transactions
        EvidenceSubtype(
            key="easypaisa_statement",
            label="Easypaisa Statement",
            category="digital_transactions",
            document_type=DocumentType.wallet_statements,
            tier="recommended",
            allow_multiple=True,
        ),
        EvidenceSubtype(
            key="jazzcash_statement",
            label="JazzCash Statement",
            category="digital_transactions",
            document_type=DocumentType.wallet_statements,
            tier="recommended",
            allow_multiple=True,
        ),
        EvidenceSubtype(
            key="bank_statement",
            label="Bank Statement",
            category="digital_transactions",
            document_type=DocumentType.wallet_statements,
            tier="recommended",
            allow_multiple=True,
        ),
        EvidenceSubtype(
            key="nayapay_statement",
            label="NayaPay Statement",
            category="digital_transactions",
            document_type=DocumentType.wallet_statements,
            tier="recommended",
            allow_multiple=True,
        ),
        EvidenceSubtype(
            key="sadapay_statement",
            label="SadaPay Statement",
            category="digital_transactions",
            document_type=DocumentType.wallet_statements,
            tier="recommended",
            allow_multiple=True,
        ),
        # ------------------------------------------------- business proof
        EvidenceSubtype(
            key="electricity_bill",
            label="Electricity Bill",
            category="business_proof",
            document_type=DocumentType.utility_bills,
            tier="recommended",
            allow_multiple=True,
        ),
        EvidenceSubtype(
            key="gas_bill",
            label="Gas Bill",
            category="business_proof",
            document_type=DocumentType.utility_bills,
            tier="optional",
            allow_multiple=True,
        ),
        EvidenceSubtype(
            key="water_bill",
            label="Water Bill",
            category="business_proof",
            document_type=DocumentType.utility_bills,
            tier="optional",
            allow_multiple=True,
        ),
        EvidenceSubtype(
            key="internet_bill",
            label="Internet Bill",
            category="business_proof",
            document_type=DocumentType.utility_bills,
            tier="optional",
            allow_multiple=True,
        ),
        EvidenceSubtype(
            key="rent_agreement",
            label="Rent Agreement",
            category="business_proof",
            document_type=DocumentType.other,
            tier="optional",
            allow_multiple=True,
        ),
        EvidenceSubtype(
            key="trade_license",
            label="Trade License",
            category="business_proof",
            document_type=DocumentType.other,
            tier="optional",
            allow_multiple=True,
        ),
        EvidenceSubtype(
            key="tax_document",
            label="Tax Document",
            category="business_proof",
            document_type=DocumentType.tax_filing,
            tier="optional",
            allow_multiple=True,
        ),
        EvidenceSubtype(
            key="supplier_invoice",
            label="Supplier Invoice",
            category="business_proof",
            document_type=DocumentType.invoice,
            tier="optional",
            allow_multiple=True,
        ),
        # ------------------------------------------------ business photos
        EvidenceSubtype(
            key="shop_front",
            label="Shop Front",
            category="business_photos",
            document_type=DocumentType.other,
            tier="required",
            allow_multiple=False,
            helper_text="A photo of your shop/business from the outside, signage visible.",
        ),
        EvidenceSubtype(
            key="shop_interior",
            label="Shop Interior",
            category="business_photos",
            document_type=DocumentType.other,
            tier="required",
            allow_multiple=False,
            helper_text="A photo from inside your business premises.",
        ),
        EvidenceSubtype(
            key="inventory_photos",
            label="Inventory Photos",
            category="business_photos",
            document_type=DocumentType.other,
            tier="optional",
            allow_multiple=True,
        ),
        # --------------------------------------------------- additional
        EvidenceSubtype(
            key="additional_evidence",
            label="Additional Evidence",
            category="additional",
            document_type=DocumentType.other,
            tier="optional",
            allow_multiple=True,
            helper_text="Anything else that supports your application: supplier contracts, purchase receipts, etc.",
        ),
    ]
}

# Subtypes whose quality/cross-check pass should attempt identity-field
# extraction (name/CNIC number/expiry) against the application, rather
# than just a generic blur/crop/glare quality pass. Used by
# app/background/tasks.py to decide which AI path to run.
IDENTITY_SUBTYPES: frozenset[str] = frozenset({"cnic_front", "cnic_back"})

# Subtypes that are pure photographic evidence (no financial fields to
# extract) -- quality assessment only, no OCR field extraction attempted.
PHOTO_SUBTYPES: frozenset[str] = frozenset({"shop_front", "shop_interior", "inventory_photos"})


TIER_ORDER: tuple[EvidenceTier, ...] = ("required", "recommended", "optional")
TIER_LABELS: dict[EvidenceTier, str] = {
    "required": "Required",
    "recommended": "Recommended",
    "optional": "Optional",
}


def get_subtype(key: str | None) -> EvidenceSubtype | None:
    if key is None:
        return None
    return EVIDENCE_SUBTYPES.get(key)


def subtypes_for_category(category: str) -> list[EvidenceSubtype]:
    return [s for s in EVIDENCE_SUBTYPES.values() if s.category == category]


def subtypes_by_tier(category: str, tier: EvidenceTier) -> list[EvidenceSubtype]:
    return [s for s in EVIDENCE_SUBTYPES.values() if s.category == category and s.tier == tier]
