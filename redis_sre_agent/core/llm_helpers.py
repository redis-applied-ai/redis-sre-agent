"""Helper functions for creating LLM clients with consistent configuration."""

from typing import Optional

from langchain_openai import ChatOpenAI

from redis_sre_agent.core.config import settings


def create_llm(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> ChatOpenAI:
    """Create a ChatOpenAI instance for main agent reasoning tasks.

    Uses the configured openai_model from settings by default.

    Args:
        model: Optional model name override. Defaults to settings.openai_model
        api_key: Optional API key override. Defaults to settings.openai_api_key
        timeout: Optional timeout override. Defaults to settings.llm_timeout
        **kwargs: Additional arguments to pass to ChatOpenAI

    Returns:
        Configured ChatOpenAI instance
    """
    llm_kwargs = {
        "model": model or settings.openai_model,
        "api_key": api_key or settings.openai_api_key,
        "timeout": timeout or settings.llm_timeout,
        **kwargs,
    }

    # Only include base_url if it's configured
    if settings.openai_base_url:
        llm_kwargs["base_url"] = settings.openai_base_url

    return ChatOpenAI(**llm_kwargs)


def create_mini_llm(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> ChatOpenAI:
    """Create a ChatOpenAI instance for knowledge/search and utility tasks.

    Uses the configured openai_model_mini from settings by default.

    Args:
        model: Optional model name override. Defaults to settings.openai_model_mini
        api_key: Optional API key override. Defaults to settings.openai_api_key
        timeout: Optional timeout override. Defaults to settings.llm_timeout
        **kwargs: Additional arguments to pass to ChatOpenAI

    Returns:
        Configured ChatOpenAI instance
    """
    llm_kwargs = {
        "model": model or settings.openai_model_mini,
        "api_key": api_key or settings.openai_api_key,
        "timeout": timeout or settings.llm_timeout,
        **kwargs,
    }

    # Only include base_url if it's configured
    if settings.openai_base_url:
        llm_kwargs["base_url"] = settings.openai_base_url

    return ChatOpenAI(**llm_kwargs)


def create_nano_llm(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> ChatOpenAI:
    """Create a ChatOpenAI instance for simple classification/triage tasks.

    Uses the configured openai_model_nano from settings by default.

    Args:
        model: Optional model name override. Defaults to settings.openai_model_nano
        api_key: Optional API key override. Defaults to settings.openai_api_key
        timeout: Optional timeout override. Defaults to settings.llm_timeout
        **kwargs: Additional arguments to pass to ChatOpenAI

    Returns:
        Configured ChatOpenAI instance
    """
    llm_kwargs = {
        "model": model or settings.openai_model_nano,
        "api_key": api_key or settings.openai_api_key,
        "timeout": timeout or settings.llm_timeout,
        **kwargs,
    }

    # Only include base_url if it's configured
    if settings.openai_base_url:
        llm_kwargs["base_url"] = settings.openai_base_url

    return ChatOpenAI(**llm_kwargs)
