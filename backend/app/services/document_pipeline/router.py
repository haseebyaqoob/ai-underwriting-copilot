"""
Module 4 routing: `utility_bills` and `wallet_statements` go through the
deterministic parsers first; only fall back to the LLM vision path
(Module 5's GeminiProvider) when overall confidence comes back below
CONFIDENCE_THRESHOLD, or no fields were found at all. `khata` is never
attempted deterministically — it goes straight to the LLM path, since no
regex/fuzzy-match approach exists for handwriting. `tax_filing`, `invoice`,
and `other` also have no deterministic parser (Module 4's spec only names
utility_bills/wallet_statements for that) and route straight to the LLM
path too.
"""
import logging

from app.db.models.enums import DocumentType
from app.services.ai import get_ai_provider
from app.services.ai.provider_base import DocumentExtractionResult
from app.services.document_pipeline import text_extraction
from app.services.document_pipeline.deterministic import utility_bill, wallet_statement
from app.services.document_pipeline.deterministic.common import CONFIDENCE_THRESHOLD, FieldResult

logger = logging.getLogger(__name__)

_DETERMINISTIC_PARSERS = {
    DocumentType.utility_bills: utility_bill.parse,
    DocumentType.wallet_statements: wallet_statement.parse,
}


class PipelineResult:
    __slots__ = ("fields", "source", "provider")

    def __init__(self, fields: list[FieldResult], source: str, provider: str | None = None):
        self.fields = fields
        self.source = source  # "deterministic" | "llm"
        self.provider = provider  # e.g. "K-Electric", "Easypaisa" — None if not applicable/detected


def process(*, file_bytes: bytes, mime_type: str, document_type: DocumentType) -> PipelineResult:
    if document_type == DocumentType.khata:
        return _run_llm(file_bytes, mime_type, document_type, reason="khata is vision-only; no deterministic parser exists for handwriting")

    parser = _DETERMINISTIC_PARSERS.get(document_type)
    if parser is None:
        return _run_llm(
            file_bytes, mime_type, document_type, reason=f"no deterministic parser registered for {document_type.value}"
        )

    text, ocr_confidence = text_extraction.extract_text(file_bytes, mime_type)
    result = parser(text, ocr_confidence=ocr_confidence)

    if result.fields and result.overall_confidence >= CONFIDENCE_THRESHOLD:
        logger.info(
            "document_pipeline: deterministic parse OK for %s (confidence=%.2f, provider=%s, fields=%d)",
            document_type.value, result.overall_confidence, result.provider, len(result.fields),
        )
        return PipelineResult(fields=result.fields, source="deterministic", provider=result.provider)

    logger.info(
        "document_pipeline: deterministic confidence %.2f (fields=%d) below threshold %.2f for %s, falling back to LLM",
        result.overall_confidence, len(result.fields), CONFIDENCE_THRESHOLD, document_type.value,
    )
    return _run_llm(file_bytes, mime_type, document_type, reason="deterministic confidence below threshold")


def _run_llm(file_bytes: bytes, mime_type: str, document_type: DocumentType, *, reason: str) -> PipelineResult:
    logger.info("document_pipeline: routing %s to LLM path (%s)", document_type.value, reason)
    provider = get_ai_provider()
    extraction: DocumentExtractionResult = provider.extract_document(
        file_bytes=file_bytes, mime_type=mime_type, document_type=document_type.value
    )
    fields = [
        FieldResult(
            field_name=f.field_name,
            field_value=f.field_value,
            value_type=f.value_type,
            confidence=f.confidence,
            source_page=f.source_page,
            bbox=f.bbox,
        )
        for f in extraction.fields
    ]
    return PipelineResult(fields=fields, source="llm", provider=None)
