"""
Provider factory — the ONE place that knows AI_PROVIDER maps to a concrete
class. Every caller (document_pipeline/router.py, and eventually whatever
calls generate_summary/generate_risk_explanation/extract_evidence_links)
imports `get_ai_provider`, never a concrete provider class directly, so
adding OpenAIProvider/ClaudeProvider later is a one-line addition here and
nowhere else.
"""
from functools import lru_cache

from app.config import settings
from app.services.ai.provider_base import LLMProvider


@lru_cache(maxsize=1)
def get_ai_provider() -> LLMProvider:
    if settings.AI_PROVIDER == "gemini":
        from app.services.ai.gemini_provider import GeminiProvider

        return GeminiProvider()

    raise ValueError(f"Unknown AI_PROVIDER: {settings.AI_PROVIDER!r}")
