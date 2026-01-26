"""Helper functions for creating LLM clients with consistent configuration.

This module provides factory functions for creating LangChain chat models.
By default, it creates ChatOpenAI instances, but users can register a custom
factory function to use different LangChain chat models (e.g., ChatAnthropic,
ChatVertexAI, ChatBedrock).

Example:
    # Register a custom factory for Anthropic
    from langchain_anthropic import ChatAnthropic

    def my_factory(tier: str, model: str | None, timeout: float | None, **kwargs):
        return ChatAnthropic(
            model=model or "claude-3-sonnet",
            timeout=timeout,
            **kwargs
        )

    set_llm_factory(my_factory)
"""

from typing import Callable, Optional, Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from redis_sre_agent.core.config import settings


class LLMFactory(Protocol):
    """Protocol for custom LLM factory functions.

    A factory function receives:
        tier: One of "main", "mini", or "nano" indicating the intended use case
        model: Optional model name override (None means use default for tier)
        timeout: Optional timeout override (None means use settings.llm_timeout)
        **kwargs: Additional arguments passed through from create_llm/mini/nano

    Returns:
        A LangChain BaseChatModel instance (ChatOpenAI, ChatAnthropic, etc.)
    """

    def __call__(
        self,
        tier: str,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> BaseChatModel: ...


# Global factory function - can be replaced by users
_llm_factory: Optional[LLMFactory] = None


def set_llm_factory(factory: Optional[LLMFactory]) -> None:
    """Register a custom LLM factory function.

    Use this to replace the default ChatOpenAI factory with a custom one
    that creates different LangChain chat models.

    Args:
        factory: A callable matching the LLMFactory protocol, or None to reset
                 to the default ChatOpenAI factory.

    Example:
        from langchain_anthropic import ChatAnthropic

        def anthropic_factory(tier, model, timeout, **kwargs):
            models = {"main": "claude-3-opus", "mini": "claude-3-sonnet", "nano": "claude-3-haiku"}
            return ChatAnthropic(
                model=model or models.get(tier, "claude-3-sonnet"),
                timeout=timeout or 180.0,
                **kwargs
            )

        set_llm_factory(anthropic_factory)
    """
    global _llm_factory
    _llm_factory = factory


def get_llm_factory() -> Optional[LLMFactory]:
    """Get the currently registered LLM factory, if any."""
    return _llm_factory


def _default_openai_factory(
    tier: str,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> ChatOpenAI:
    """Default factory that creates ChatOpenAI instances.

    Args:
        tier: One of "main", "mini", or "nano"
        model: Optional model name override
        timeout: Optional timeout override
        **kwargs: Additional arguments to pass to ChatOpenAI

    Returns:
        Configured ChatOpenAI instance
    """
    # Get default model based on tier
    default_models = {
        "main": settings.openai_model,
        "mini": settings.openai_model_mini,
        "nano": settings.openai_model_nano,
    }
    default_model = default_models.get(tier, settings.openai_model)

    llm_kwargs = {
        "model": model or default_model,
        "api_key": kwargs.pop("api_key", None) or settings.openai_api_key,
        "timeout": timeout or settings.llm_timeout,
        **kwargs,
    }

    # Only include base_url if it's configured
    if settings.openai_base_url:
        llm_kwargs["base_url"] = settings.openai_base_url

    return ChatOpenAI(**llm_kwargs)


def _create_llm_with_factory(
    tier: str,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> BaseChatModel:
    """Create an LLM using the registered factory or default.

    Args:
        tier: One of "main", "mini", or "nano"
        model: Optional model name override
        timeout: Optional timeout override
        **kwargs: Additional arguments passed to factory

    Returns:
        Configured LangChain chat model instance
    """
    factory = _llm_factory if _llm_factory is not None else _default_openai_factory
    return factory(tier=tier, model=model, timeout=timeout, **kwargs)


def create_llm(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> BaseChatModel:
    """Create a chat model instance for main agent reasoning tasks.

    Uses the configured openai_model from settings by default.
    If a custom factory is registered via set_llm_factory(), it will be used
    instead of the default ChatOpenAI factory.

    Args:
        model: Optional model name override. Defaults to settings.openai_model
        api_key: Optional API key override. Defaults to settings.openai_api_key
        timeout: Optional timeout override. Defaults to settings.llm_timeout
        **kwargs: Additional arguments to pass to the LLM factory

    Returns:
        Configured LangChain chat model instance
    """
    if api_key is not None:
        kwargs["api_key"] = api_key
    return _create_llm_with_factory(
        tier="main",
        model=model,
        timeout=timeout,
        **kwargs,
    )


def create_mini_llm(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> BaseChatModel:
    """Create a chat model instance for knowledge/search and utility tasks.

    Uses the configured openai_model_mini from settings by default.
    If a custom factory is registered via set_llm_factory(), it will be used
    instead of the default ChatOpenAI factory.

    Args:
        model: Optional model name override. Defaults to settings.openai_model_mini
        api_key: Optional API key override. Defaults to settings.openai_api_key
        timeout: Optional timeout override. Defaults to settings.llm_timeout
        **kwargs: Additional arguments to pass to the LLM factory

    Returns:
        Configured LangChain chat model instance
    """
    if api_key is not None:
        kwargs["api_key"] = api_key
    return _create_llm_with_factory(
        tier="mini",
        model=model,
        timeout=timeout,
        **kwargs,
    )


def create_nano_llm(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> BaseChatModel:
    """Create a chat model instance for simple classification/triage tasks.

    Uses the configured openai_model_nano from settings by default.
    If a custom factory is registered via set_llm_factory(), it will be used
    instead of the default ChatOpenAI factory.

    Args:
        model: Optional model name override. Defaults to settings.openai_model_nano
        api_key: Optional API key override. Defaults to settings.openai_api_key
        timeout: Optional timeout override. Defaults to settings.llm_timeout
        **kwargs: Additional arguments to pass to the LLM factory

    Returns:
        Configured LangChain chat model instance
    """
    if api_key is not None:
        kwargs["api_key"] = api_key
    return _create_llm_with_factory(
        tier="nano",
        model=model,
        timeout=timeout,
        **kwargs,
    )
