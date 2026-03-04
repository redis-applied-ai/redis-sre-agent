"""Helper functions for creating LLM clients with consistent configuration.

This module provides factory functions for:
- LangChain chat models (BaseChatModel)
- OpenAI async SDK clients (AsyncOpenAI)

By default, it creates ChatOpenAI / AsyncOpenAI instances, but users can
configure custom factory functions.

Configuration:
    Set factory environment variables to dot-path import strings:

    LLM_FACTORY=mypackage.llm.anthropic_factory
    ASYNC_OPENAI_CLIENT_FACTORY=mypackage.llm.async_openai_factory

    Factory functions must match the corresponding protocol signatures.

Programmatic registration:
    from redis_sre_agent.core.llm_helpers import set_llm_factory
    from langchain_anthropic import ChatAnthropic

    def my_factory(tier: str, model: str | None, timeout: float | None, **kwargs):
        return ChatAnthropic(
            model=model or "claude-3-sonnet",
            timeout=timeout,
            **kwargs
        )

    set_llm_factory(my_factory)
"""

import importlib
import logging
from typing import Optional, Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

from redis_sre_agent.core.config import settings

logger = logging.getLogger(__name__)


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


class AsyncOpenAIClientFactory(Protocol):
    """Protocol for custom AsyncOpenAI client factory functions.

    A factory function receives:
        tier: One of "main", "mini", or "nano" indicating the intended use case
        model: Optional model name hint for custom factories
        api_key: Optional API key override
        timeout: Optional timeout override
        **kwargs: Additional arguments passed through from client helpers

    Returns:
        An OpenAI-compatible async client (typically openai.AsyncOpenAI)
    """

    def __call__(
        self,
        tier: str,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> AsyncOpenAI: ...


# Global factory function - can be replaced by users or loaded from config
_llm_factory: Optional[LLMFactory] = None
_factory_initialized: bool = False
_async_openai_client_factory: Optional[AsyncOpenAIClientFactory] = None
_async_openai_factory_initialized: bool = False


def _load_factory_from_config() -> None:
    """Load the LLM factory from config if specified.

    Called automatically on first LLM creation. Users can also call
    set_llm_factory() to override programmatically.
    """
    global _llm_factory, _factory_initialized

    if _factory_initialized:
        return

    _factory_initialized = True

    # Check if llm_factory is set and is a non-empty string
    llm_factory_path = getattr(settings, "llm_factory", None)
    if not llm_factory_path or not isinstance(llm_factory_path, str):
        return

    try:
        # Parse dot-path: "mypackage.module.function_name"
        module_path, _, func_name = llm_factory_path.rpartition(".")
        if not module_path:
            raise ValueError(
                f"Invalid LLM_FACTORY path '{llm_factory_path}': "
                "must be a dot-path like 'mypackage.module.factory_func'"
            )

        module = importlib.import_module(module_path)
        factory = getattr(module, func_name)

        if not callable(factory):
            raise ValueError(f"LLM_FACTORY '{llm_factory_path}' is not callable")

        _llm_factory = factory
        logger.info(f"Loaded custom LLM factory from {llm_factory_path}")

    except Exception as e:
        logger.error(f"Failed to load LLM factory from '{llm_factory_path}': {e}")
        raise


def _load_async_openai_factory_from_config() -> None:
    """Load the AsyncOpenAI client factory from config if specified."""
    global _async_openai_client_factory, _async_openai_factory_initialized

    if _async_openai_factory_initialized:
        return

    _async_openai_factory_initialized = True

    factory_path = getattr(settings, "async_openai_client_factory", None)
    if not factory_path or not isinstance(factory_path, str):
        return

    try:
        module_path, _, func_name = factory_path.rpartition(".")
        if not module_path:
            raise ValueError(
                f"Invalid ASYNC_OPENAI_CLIENT_FACTORY path '{factory_path}': "
                "must be a dot-path like 'mypackage.module.factory_func'"
            )

        module = importlib.import_module(module_path)
        factory = getattr(module, func_name)

        if not callable(factory):
            raise ValueError(f"ASYNC_OPENAI_CLIENT_FACTORY '{factory_path}' is not callable")

        _async_openai_client_factory = factory
        logger.info(f"Loaded custom AsyncOpenAI client factory from {factory_path}")
    except Exception as e:
        logger.error(f"Failed to load AsyncOpenAI client factory from '{factory_path}': {e}")
        raise


def set_llm_factory(factory: Optional[LLMFactory]) -> None:
    """Register a custom LLM factory function.

    Use this to replace the default ChatOpenAI factory with a custom one
    that creates different LangChain chat models. This overrides any factory
    configured via LLM_FACTORY environment variable.

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
    global _llm_factory, _factory_initialized
    _llm_factory = factory
    _factory_initialized = True  # Mark as initialized to prevent config override


def set_async_openai_client_factory(factory: Optional[AsyncOpenAIClientFactory]) -> None:
    """Register a custom AsyncOpenAI client factory function.

    This overrides any factory configured via ASYNC_OPENAI_CLIENT_FACTORY.
    """
    global _async_openai_client_factory, _async_openai_factory_initialized
    _async_openai_client_factory = factory
    _async_openai_factory_initialized = True


def get_llm_factory() -> Optional[LLMFactory]:
    """Get the currently registered LLM factory, if any.

    Note: This does not trigger loading from config. Use create_llm() etc.
    to ensure the factory is loaded from config if not already set.
    """
    return _llm_factory


def get_async_openai_client_factory() -> Optional[AsyncOpenAIClientFactory]:
    """Get the currently registered AsyncOpenAI client factory, if any."""
    return _async_openai_client_factory


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


def _default_async_openai_client_factory(
    tier: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> AsyncOpenAI:
    """Default factory that creates AsyncOpenAI instances.

    Args:
        tier: One of "main", "mini", or "nano" (informational for default factory)
        model: Optional model hint (unused by default factory)
        api_key: Optional API key override
        timeout: Optional timeout override
        **kwargs: Additional arguments to pass to AsyncOpenAI

    Returns:
        Configured AsyncOpenAI instance
    """
    # tier/model are part of the protocol for custom factories; default client
    # initialization does not require them.
    del tier, model

    client_kwargs = {
        "api_key": api_key or settings.openai_api_key,
        "timeout": timeout if timeout is not None else settings.llm_timeout,
        **kwargs,
    }
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    return AsyncOpenAI(**client_kwargs)


def _create_llm_with_factory(
    tier: str,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> BaseChatModel:
    """Create an LLM using the registered factory or default.

    On first call, loads the factory from LLM_FACTORY config if set.

    Args:
        tier: One of "main", "mini", or "nano"
        model: Optional model name override
        timeout: Optional timeout override
        **kwargs: Additional arguments passed to factory

    Returns:
        Configured LangChain chat model instance
    """
    # Load factory from config on first use (if not already set programmatically)
    _load_factory_from_config()

    factory = _llm_factory if _llm_factory is not None else _default_openai_factory
    return factory(tier=tier, model=model, timeout=timeout, **kwargs)


def _create_async_openai_client_with_factory(
    tier: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> AsyncOpenAI:
    """Create an AsyncOpenAI client using the registered factory or default."""
    _load_async_openai_factory_from_config()
    factory = (
        _async_openai_client_factory
        if _async_openai_client_factory is not None
        else _default_async_openai_client_factory
    )
    return factory(
        tier=tier,
        model=model,
        api_key=api_key,
        timeout=timeout,
        **kwargs,
    )


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


def create_async_openai_client(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> AsyncOpenAI:
    """Create an AsyncOpenAI client for main tasks."""
    return _create_async_openai_client_with_factory(
        tier="main",
        model=model,
        api_key=api_key,
        timeout=timeout,
        **kwargs,
    )


def create_mini_async_openai_client(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> AsyncOpenAI:
    """Create an AsyncOpenAI client for utility/knowledge tasks."""
    return _create_async_openai_client_with_factory(
        tier="mini",
        model=model,
        api_key=api_key,
        timeout=timeout,
        **kwargs,
    )


def create_nano_async_openai_client(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> AsyncOpenAI:
    """Create an AsyncOpenAI client for simple/fast tasks."""
    return _create_async_openai_client_with_factory(
        tier="nano",
        model=model,
        api_key=api_key,
        timeout=timeout,
        **kwargs,
    )
