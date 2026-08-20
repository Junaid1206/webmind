"""LLM provider abstraction for synthesizing research results."""

from backend.app.services.llm.provider import (
    LLMProvider,
    LLMResponse,
    OpenAICompatibleLLMProvider,
)
from backend.app.services.llm.research_synthesizer import (
    ResearchContext,
    ResearchSynthesis,
    ResearchSynthesizer,
)

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "OpenAICompatibleLLMProvider",
    "ResearchContext",
    "ResearchSynthesis",
    "ResearchSynthesizer",
]
