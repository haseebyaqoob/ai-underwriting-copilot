"""
Concrete Gemini implementation of LLMProvider — Module 5.

Uses the `google-genai` SDK's structured-output support (`response_schema`
pinned to a Pydantic model) for the two methods that need reliably parseable
output (extract_document, extract_evidence_links), and plain text generation
for the two narrative methods (generate_summary, generate_risk_explanation).

IMPORTANT — testing status (see docs/ARCHITECTURE_AND_PROGRESS.md, Module 5
section, for the full account): this was NOT exercised against a live
Gemini API key. This sandbox's network egress allowlist doesn't include
Google's API domains, and no GEMINI_API_KEY was provided. The original four
methods were exercised against a monkeypatched `genai.Client` returning
canned-but-realistic responses, verifying the request-shaping and
response-parsing logic. The actual HTTP call to Gemini is untested.

Evidence Checklist addition (`assess_quality`, this session): same
environment constraint applied -- no live key, no network to Google. Only
verified by static review + `py_compile`, not exercised against a
monkeypatched client or a real call. Treat it as unverified until a real
GEMINI_API_KEY + network-accessible environment runs it end-to-end.
"""
import logging

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.config import settings
from app.services.ai.provider_base import (
    DocumentExtractionResult,
    DocumentTypeCheck,
    EvidenceLink,
    ExtractedFieldResult,
    LLMProvider,
    QualityAssessment,
)

logger = logging.getLogger(__name__)


# --- Gemini-only structured-output schemas -----------------------------
# These stay inside this file on purpose — they're an SDK implementation
# detail of *how* GeminiProvider gets reliable JSON back, not part of the
# provider-agnostic contract in provider_base.py.
class _GeminiFieldSchema(BaseModel):
    field_name: str
    field_value: str
    value_type: str
    confidence: float
    source_page: int | None = None


class _GeminiExtractionSchema(BaseModel):
    fields: list[_GeminiFieldSchema]
    notes: str | None = None


class _GeminiEvidenceLinkSchema(BaseModel):
    field_name: str
    document_version_id: str
    source_page: int | None = None
    note: str


class _GeminiEvidenceLinksSchema(BaseModel):
    links: list[_GeminiEvidenceLinkSchema]


class _GeminiTypeCheckSchema(BaseModel):
    matches: bool
    detected_label: str
    confidence: float
    reason: str


class _GeminiQualitySchema(BaseModel):
    status: str  # "verified" | "needs_better_image"
    issues: list[str]
    guidance: str | None = None
    extracted_name: str | None = None
    extracted_id_number: str | None = None
    extracted_expiry_date: str | None = None


_TYPE_CHECK_PROMPT_TEMPLATE = """You are a document intake classifier for a small business loan application in Pakistan.

The applicant was asked to upload: "{expected_label}".

Look at the attached file and decide whether it actually is that kind of document. Be specific about what you actually see -- if it's clearly a different kind of document (e.g. a school transcript, a photo of a person, a blank page, a screenshot of a chat app), say so plainly.

Return:
- matches: true only if the document is genuinely a "{expected_label}" (or an obvious equivalent/variant of it, e.g. a slightly different bank's statement layout still counts as a bank statement). false for anything else, including illegible files you cannot classify with reasonable confidence -- when in doubt, prefer false with an honest low confidence over guessing true.
- detected_label: a short, human-readable name for what the document actually appears to be (e.g. "Academic Transcript", "Electricity Bill", "Selfie Photo"). Never leave this blank.
- confidence: your confidence in THIS classification, 0.0 to 1.0. Be conservative -- a blurry or partial image should get a lower confidence, not a confident wrong guess.
- reason: one short, specific sentence explaining the verdict, e.g. "This shows a printed transcript with course grades, not a utility bill" or "This is a K-Electric bill with a consumer number and billing month, matching the expected document."

Do not evaluate document authenticity, only document type. Never invent details you cannot see.
"""

_EXTRACTION_PROMPT_TEMPLATE = """You are an underwriting document analyst reviewing a {document_type} for a small business loan application in Pakistan.

Extract every relevant structured field you can confidently read from the attached image. Field names should be short snake_case identifiers (e.g. "amount_payable", "entry_date", "entry_amount", "entry_description"). For a khata (handwritten ledger), extract each line item as a separate set of fields (e.g. "line_1_date", "line_1_description", "line_1_amount", "line_2_date", ...).

For every field, give:
- field_value: the value as plain text
- value_type: one of "string", "number", "date"
- confidence: your confidence in this specific reading, from 0.0 to 1.0 — be honest and conservative, especially for handwriting that's ambiguous, smudged, or could be read more than one way
- source_page: the page number this came from (1-indexed), if the document has multiple pages, otherwise omit

Hard rules, follow them exactly:
- NEVER invent, infer, or estimate a value that is not actually visible on the document. If a field is not present, not legible, or you are not reasonably sure what it says, do not include it at all rather than reporting a guess.
- Do not "fill in" a field just because a document of this type usually has one -- absence is a valid, expected outcome, not an error to paper over.
- If the document is illegible, water-damaged, or otherwise unreadable in parts, say so plainly in `notes` rather than guessing at values and reporting them as high-confidence.
- confidence must reflect genuine uncertainty. Do not default every field to a high round number (e.g. 0.95) out of habit -- vary it honestly based on how legible each specific value actually is.
"""

_SUMMARY_PROMPT_TEMPLATE = """You are writing a concise financial summary for a loan officer reviewing "{business_name}"'s small business loan application.

Here are the extracted financial data points gathered from the applicant's submitted documents:
{fields_block}

Write a plain-English summary (3-5 sentences) of what this data shows about the business's cash flow and financial standing. Be factual and specific to the numbers given — do not invent figures that aren't in the data above. Do not make an approve/reject recommendation; that decision belongs to the loan officer, not you.
"""

_RISK_EXPLANATION_PROMPT_TEMPLATE = """You are explaining a risk score to a loan officer reviewing "{business_name}"'s small business loan application.

The deterministic risk engine (not you) computed:
- Overall score: {score}/1000
- Contribution breakdown: {contributions}

Supporting extracted data:
{fields_block}

Write a plain-English explanation (3-5 sentences) of why the score likely landed where it did, referencing the contribution breakdown and the supporting data. Do not change, second-guess, or restate a different score than the one given — your job is only to explain the number that was already computed, not to compute or revise it.
"""


_QUALITY_PROMPT_TEMPLATE = """You are a document intake quality checker for a small business loan application in Pakistan. You are reviewing an uploaded {document_type} image/scan.

Your ONLY job is to judge whether this image is USABLE for a human reviewer to read later. You are NOT judging whether the document is genuine, unaltered, or issued by a real authority -- do not comment on authenticity at all, only on image quality and legibility.

Check for these specific problems:
- blur (out of focus / camera shake)
- glare (light reflection obscuring text, common with laminated cards and glossy paper)
- low_resolution (image too small/compressed to read fine print)
- cropped (part of the document is cut off, corners missing)
- unreadable (illegible for any other reason -- water damage, extreme darkness, etc.)

If you find one or more of these, set status to "needs_better_image", list every issue you found in `issues` (using exactly the snake_case names above), and write one short, specific, actionable sentence in `guidance` telling the applicant what to do differently (e.g. "Please retake the photo in better lighting, away from direct glare." or "Please include all four corners of the card in the frame."). If the image is genuinely fine, set status to "verified", leave `issues` empty, and leave `guidance` null.

{identity_instructions}
"""

_IDENTITY_INSTRUCTIONS = """This is a Pakistani CNIC (national identity card). If -- and only if -- the image quality is good enough to read clearly, also extract:
- extracted_name: the full name printed on the card
- extracted_id_number: the 13-digit CNIC number, formatted as it appears (e.g. 42101-1234567-1)
- extracted_expiry_date: the expiry date as printed

If the card is a "back" side with no name/number printed, leave those fields null. If the image quality is too poor to read a field confidently, leave it null rather than guessing -- do not report a low-confidence guess as if it were a reliable reading."""

_NON_IDENTITY_INSTRUCTIONS = "This document is not an identity document -- do not attempt to extract a name or ID number; leave extracted_name/extracted_id_number/extracted_expiry_date null."


def _fields_block(fields: list[ExtractedFieldResult]) -> str:
    if not fields:
        return "(no extracted fields available)"
    return "\n".join(f"- {f.field_name}: {f.field_value} (confidence: {f.confidence:.2f})" for f in fields)


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model_name: str | None = None):
        api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        if not api_key:
            # Fail fast and loudly rather than silently no-op'ing or
            # returning empty results that would look like "the document
            # had nothing extractable" instead of "this isn't configured".
            raise ValueError(
                "GeminiProvider requires GEMINI_API_KEY to be set. "
                "Set it in .env, or pass api_key= explicitly (e.g. for tests)."
            )
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name or settings.GEMINI_MODEL_NAME

    # -------------------------------------------------------- type check
    def check_document_type(
        self, *, file_bytes: bytes, mime_type: str, expected_label: str
    ) -> DocumentTypeCheck:
        prompt = _TYPE_CHECK_PROMPT_TEMPLATE.format(expected_label=expected_label)
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_GeminiTypeCheckSchema,
                temperature=0.0,  # classification, not creative -- lock this down hard
            ),
        )
        parsed: _GeminiTypeCheckSchema = self._parse_or_raise(response, _GeminiTypeCheckSchema)
        return DocumentTypeCheck(
            matches=bool(parsed.matches),
            detected_label=parsed.detected_label or "Unrecognized document",
            confidence=max(0.0, min(1.0, parsed.confidence)),
            reason=parsed.reason or "",
        )

    # ------------------------------------------------------------ extract
    def extract_document(self, *, file_bytes: bytes, mime_type: str, document_type: str) -> DocumentExtractionResult:
        prompt = _EXTRACTION_PROMPT_TEMPLATE.format(document_type=document_type)
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_GeminiExtractionSchema,
                temperature=0.1,  # extraction should be deterministic-leaning, not creative
            ),
        )
        parsed: _GeminiExtractionSchema = self._parse_or_raise(response, _GeminiExtractionSchema)
        fields = [
            ExtractedFieldResult(
                field_name=f.field_name,
                field_value=f.field_value,
                value_type=f.value_type,
                confidence=max(0.0, min(1.0, f.confidence)),
                source_page=f.source_page,
            )
            for f in parsed.fields
        ]
        return DocumentExtractionResult(fields=fields, raw_notes=parsed.notes)

    # -------------------------------------------------------------- text
    def generate_summary(self, *, business_name: str, fields: list[ExtractedFieldResult]) -> str:
        prompt = _SUMMARY_PROMPT_TEMPLATE.format(business_name=business_name, fields_block=_fields_block(fields))
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=[prompt],
            config=types.GenerateContentConfig(temperature=0.4),
        )
        return self._text_or_raise(response)

    def generate_risk_explanation(
        self, *, business_name: str, score: int, contributions: dict[str, int], fields: list[ExtractedFieldResult]
    ) -> str:
        prompt = _RISK_EXPLANATION_PROMPT_TEMPLATE.format(
            business_name=business_name, score=score, contributions=contributions, fields_block=_fields_block(fields)
        )
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=[prompt],
            config=types.GenerateContentConfig(temperature=0.4),
        )
        return self._text_or_raise(response)

    # ---------------------------------------------------------- evidence
    def extract_evidence_links(self, *, fields: list[ExtractedFieldResult]) -> list[EvidenceLink]:
        if not fields:
            return []
        prompt = (
            "Given these extracted fields (each already tagged with the document/page it came from where "
            "available), group and describe how they support each other as underwriting evidence. "
            "Return one link entry per meaningful field.\n\n" + _fields_block(fields)
        )
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_GeminiEvidenceLinksSchema,
                temperature=0.2,
            ),
        )
        parsed: _GeminiEvidenceLinksSchema = self._parse_or_raise(response, _GeminiEvidenceLinksSchema)
        return [
            EvidenceLink(
                field_name=link.field_name,
                document_version_id=link.document_version_id,
                source_page=link.source_page,
                note=link.note,
            )
            for link in parsed.links
        ]

    # ----------------------------------------------------------- quality
    def assess_quality(
        self, *, file_bytes: bytes, mime_type: str, document_type: str, is_identity_document: bool
    ) -> QualityAssessment:
        prompt = _QUALITY_PROMPT_TEMPLATE.format(
            document_type=document_type,
            identity_instructions=_IDENTITY_INSTRUCTIONS if is_identity_document else _NON_IDENTITY_INSTRUCTIONS,
        )
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_GeminiQualitySchema,
                temperature=0.1,
            ),
        )
        parsed: _GeminiQualitySchema = self._parse_or_raise(response, _GeminiQualitySchema)
        status = parsed.status if parsed.status in ("verified", "needs_better_image") else "needs_better_image"
        return QualityAssessment(
            status=status,
            issues=list(parsed.issues or []),
            guidance=parsed.guidance,
            extracted_name=parsed.extracted_name,
            extracted_id_number=parsed.extracted_id_number,
            extracted_expiry_date=parsed.extracted_expiry_date,
        )

    # ------------------------------------------------------------- utils
    @staticmethod
    def _parse_or_raise(response, schema: type[BaseModel]):
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            return parsed
        # Fallback: some SDK versions/response shapes only populate `.text`
        # even when a response_schema was given. Parse it manually rather
        # than silently returning an empty result.
        text = getattr(response, "text", None)
        if not text:
            raise ValueError("GeminiProvider: empty response from model (no .parsed or .text)")
        return schema.model_validate_json(text)

    @staticmethod
    def _text_or_raise(response) -> str:
        text = getattr(response, "text", None)
        if not text:
            raise ValueError("GeminiProvider: empty text response from model")
        return text.strip()
