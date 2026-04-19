"""LLM factory with multi-provider support and model tier routing.

Supports: Groq (free), OpenAI, Anthropic, Google Gemini, Ollama (local).
All providers return LangChain's BaseChatModel — the graph and tools
don't know or care which provider is behind the call.

Environment presets:
  development → Groq free tier (llama-3.3-70b)  $0.00
  production  → OpenAI (gpt-4o-mini / gpt-4o)   paid
"""

from __future__ import annotations

import logging
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

ModelTier = Literal["fast", "power"]

MODEL_COSTS: dict[str, dict[str, float]] = {
    # Groq (free tier)
    "llama-3.3-70b-versatile":  {"input": 0.00, "output": 0.00},
    "llama-3.1-8b-instant":     {"input": 0.00, "output": 0.00},
    "gemma2-9b-it":             {"input": 0.00, "output": 0.00},
    "mixtral-8x7b-32768":       {"input": 0.00, "output": 0.00},
    # OpenAI
    "gpt-4o-mini":              {"input": 0.15, "output": 0.60},
    "gpt-4o":                   {"input": 2.50, "output": 10.00},
    "gpt-4.1-mini":             {"input": 0.40, "output": 1.60},
    "gpt-4.1":                  {"input": 2.00, "output": 8.00},
    "gpt-4.1-nano":             {"input": 0.10, "output": 0.40},
    # Anthropic
    "claude-3-haiku-20240307":      {"input": 0.25,  "output": 1.25},
    "claude-3-5-sonnet-20241022":   {"input": 3.00,  "output": 15.00},
    "claude-sonnet-4-20250514":     {"input": 3.00,  "output": 15.00},
    # Google
    "gemini-2.0-flash":         {"input": 0.10, "output": 0.40},
    "gemini-2.5-pro":           {"input": 1.25, "output": 10.00},
    # Ollama (local, free)
    "ollama/*":                 {"input": 0.00, "output": 0.00},
}


def get_model_cost(model_name: str) -> dict[str, float]:
    if model_name in MODEL_COSTS:
        return MODEL_COSTS[model_name]
    for key in MODEL_COSTS:
        if key.endswith("/*") and model_name.startswith(key[:-2]):
            return MODEL_COSTS[key]
    return {"input": 0.0, "output": 0.0}


def _build_groq(model: str, temperature: float) -> BaseChatModel:
    settings = get_settings()
    from langchain_groq import ChatGroq
    return ChatGroq(
        model=model,
        temperature=temperature,
        api_key=settings.groq_api_key,
    )


def _build_openai(model: str, temperature: float) -> BaseChatModel:
    settings = get_settings()
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=settings.openai_api_key,
    )


def _build_anthropic(model: str, temperature: float) -> BaseChatModel:
    settings = get_settings()
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        raise RuntimeError("pip install langchain-anthropic")
    return ChatAnthropic(
        model=model,
        temperature=temperature,
        api_key=settings.anthropic_api_key,
    )


def _build_google(model: str, temperature: float) -> BaseChatModel:
    settings = get_settings()
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        raise RuntimeError("pip install langchain-google-genai")
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        google_api_key=settings.google_api_key,
    )


def _build_ollama(model: str, temperature: float) -> BaseChatModel:
    settings = get_settings()
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        base_url=f"{settings.ollama_base_url}/v1",
        api_key="ollama",
    )


_PROVIDERS = {
    "groq": _build_groq,
    "openai": _build_openai,
    "anthropic": _build_anthropic,
    "google": _build_google,
    "ollama": _build_ollama,
}


def get_llm(tier: ModelTier = "fast") -> BaseChatModel:
    """Get an LLM instance for the given tier. Provider and model
    are resolved from environment presets unless explicitly overridden."""
    settings = get_settings()
    provider = settings.resolved_provider
    model = settings.resolved_model_fast if tier == "fast" else settings.resolved_model_power

    builder = _PROVIDERS.get(provider)
    if builder is None:
        raise ValueError(
            f"Unknown LLM provider '{provider}'. "
            f"Supported: {', '.join(_PROVIDERS.keys())}"
        )

    logger.debug("LLM: provider=%s tier=%s model=%s", provider, tier, model)
    return builder(model, settings.llm_temperature)


def get_active_model_name(tier: ModelTier = "fast") -> str:
    settings = get_settings()
    return settings.resolved_model_fast if tier == "fast" else settings.resolved_model_power
