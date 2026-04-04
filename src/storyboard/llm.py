from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel

from core.config import AgentLLMConfig


def create_llm(cfg: AgentLLMConfig) -> BaseChatModel:
    """Instantiate a LangChain chat model from an AgentLLMConfig.

    Supported providers:
    - ``anthropic``  → ChatAnthropic
    - ``openai``     → ChatOpenAI
    - ``google`` / ``gemini`` → ChatGoogleGenerativeAI
    - ``mistral``    → ChatOpenAI with Mistral base_url (OpenAI-compatible)
    - ``vllm``       → ChatOpenAI with custom base_url (OpenAI-compatible)
    """
    provider = cfg.provider.lower()

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=cfg.model,
            temperature=cfg.temperature,
            **({"api_key": cfg.api_key} if cfg.api_key else {}),
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=cfg.model,
            temperature=cfg.temperature,
            **({"api_key": cfg.api_key} if cfg.api_key else {}),
            **({"base_url": cfg.base_url} if cfg.base_url else {}),
            **({"default_headers": cfg.extra_headers} if cfg.extra_headers else {}),
        )

    if provider in ("google", "gemini"):
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=cfg.model,
            temperature=cfg.temperature,
            **({"google_api_key": cfg.api_key} if cfg.api_key else {}),
        )

    if provider == "mistral":
        from langchain_mistralai import ChatMistralAI

        return ChatMistralAI(
            model=cfg.model,
            temperature=cfg.temperature,
            **({"mistral_api_key": cfg.api_key} if cfg.api_key else {}),
            **({"endpoint": cfg.base_url} if cfg.base_url else {}),
        )

    if provider == "vllm":
        from langchain_openai import ChatOpenAI

        api_key = cfg.api_key or os.environ.get("OPENAI_API_KEY", "placeholder")
        return ChatOpenAI(
            model=cfg.model,
            temperature=cfg.temperature,
            api_key=api_key,
            **({"base_url": cfg.base_url} if cfg.base_url else {}),
            **({"default_headers": cfg.extra_headers} if cfg.extra_headers else {}),
        )

    raise ValueError(
        f"Unsupported LLM provider: '{cfg.provider}'. "
        "Choose one of: anthropic, openai, google, gemini, mistral, vllm."
    )
