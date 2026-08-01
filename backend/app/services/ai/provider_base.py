
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ExtractedFieldResult:


    field_name: str
    field_value: str
    value_type: str  # "string" | "number" | "date"
    confidence: float  # 0.0-1.0
    source_page: int | None = None
    bbox: dict | None = None


@dataclass
class DocumentExtractionResult:
    fields: list[ExtractedFieldResult]
    raw_notes: str | None = None  # free-text model commentary, if any (e.g. "ledger is water-damaged on page 3")


@dataclass
class DocumentTypeCheck:


    matches: bool
    detected_label: str  # what the model thinks this document actually is
    confidence: float  # 0.0-1.0, confidence in the classification itself
    reason: str  # short, human-readable explanation either way


@dataclass
class EvidenceLink:
    """Ties a claim/field back to the specific document + page it came
    from, for the officer review UI's evidence-highlighting feature."""

    field_name: str
    document_version_id: str
    source_page: int | None
    note: str


@dataclass
class QualityAssessment:


    status: str  # "verified" | "needs_better_image"
    issues: list[str]  # e.g. ["blur", "glare", "low_resolution", "cropped"]
    guidance: str | None  # actionable, e.g. "Please retake the photo in better lighting."
    extracted_name: str | None = None  # identity documents only
    extracted_id_number: str | None = None  # identity documents only
    extracted_expiry_date: str | None = None  # identity documents only


class LLMProvider(ABC):
    @abstractmethod
    def check_document_type(
        self, *, file_bytes: bytes, mime_type: str, expected_label: str
    ) -> DocumentTypeCheck:
  
    @abstractmethod
    def extract_document(self, *, file_bytes: bytes, mime_type: str, document_type: str) -> DocumentExtractionResult:
       

    @abstractmethod
    def generate_summary(self, *, business_name: str, fields: list[ExtractedFieldResult]) -> str:
     

    @abstractmethod
    def generate_risk_explanation(
        self, *, business_name: str, score: int, contributions: dict[str, int], fields: list[ExtractedFieldResult]
    ) -> str:
       
    @abstractmethod
    def extract_evidence_links(self, *, fields: list[ExtractedFieldResult]) -> list[EvidenceLink]:
       

    @abstractmethod
    def assess_quality(
        self, *, file_bytes: bytes, mime_type: str, document_type: str, is_identity_document: bool
    ) -> QualityAssessment:
        
