
import io
import logging

import pdfplumber
import pillow_heif
import pytesseract
from PIL import Image

pillow_heif.register_heif_opener()  # lets PIL.Image.open() read .heic/.heif directly

logger = logging.getLogger(__name__)

_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/heic", "image/heif"}


def extract_text(file_bytes: bytes, mime_type: str) -> tuple[str, float | None]:
  
    try:
        if mime_type == "application/pdf":
            return _extract_pdf_text(file_bytes), None
        if mime_type in _IMAGE_MIME_TYPES:
            return _extract_image_text(file_bytes)
    except Exception:
        logger.exception("text_extraction: failed to extract text from %s file, treating as empty", mime_type)
        return "", 0.0

    logger.warning("text_extraction: no handler for mime type %s", mime_type)
    return "", 0.0


def _extract_pdf_text(file_bytes: bytes) -> str:
    text_parts: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts)


def _extract_image_text(file_bytes: bytes) -> tuple[str, float]:
    image = Image.open(io.BytesIO(file_bytes))
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    confidences: list[float] = []
    for word, conf in zip(data["text"], data["conf"]):
        if not word.strip():
            continue
        try:
            c = float(conf)
        except (TypeError, ValueError):
            continue
        if c >= 0:  # tesseract uses -1 for non-text regions
            confidences.append(c)

    text = pytesseract.image_to_string(image)
    avg_conf = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
    return text, round(avg_conf, 4)
