from __future__ import annotations

from typing import Iterable, Optional

from app.settings import get_settings

_POSITIVE_KEYWORDS: tuple[str, ...] = (
    "vision",
    "multimodal",
    "image",
    "gpt-4o",
    "gpt4o",
    "gpt-4.1",
    "gpt4.1",
    "gpt-4v",
    "claude-3.5",
    "claude-3-opus",
    "sonnet",
    "omni",
    "llava",
)

_NEGATIVE_KEYWORDS: tuple[str, ...] = (
    "gpt-3.5",
    "gpt-3.1",
    "text-only",
    "text",
    "embedding",
    "rerank",
    "tts",
    "whisper",
    "audio",
    "speech",
)

_FALLBACK_OPENROUTER_MODEL = "openai/gpt-4o-mini"
_FALLBACK_AGENTROUTER_MODEL = "gpt-4o-mini"

settings = get_settings()


def _normalize(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _normalize_many(values: Iterable[str]) -> set[str]:
    return {_normalize(item) for item in values if item}


def model_supports_vision(provider: str, model: Optional[str]) -> bool:
    """
    Decide whether a provider/model pair supports image inputs.
    Uses optional allowlists from settings, otherwise falls back to keyword heuristics.
    """
    provider_norm = _normalize(provider)
    model_norm = _normalize(model)

    if not model_norm:
        return False

    if provider_norm == "agentrouter":
        allowlist = _normalize_many(settings.agentrouter_vision_models)
    else:
        allowlist = _normalize_many(settings.openrouter_vision_models)

    if allowlist:
        return model_norm in allowlist

    if any(marker in model_norm for marker in _NEGATIVE_KEYWORDS):
        return False

    return any(marker in model_norm for marker in _POSITIVE_KEYWORDS)


def fallback_vision_model(provider: str) -> Optional[str]:
    provider_norm = _normalize(provider)
    if provider_norm == "agentrouter":
        return _FALLBACK_AGENTROUTER_MODEL
    return _FALLBACK_OPENROUTER_MODEL
