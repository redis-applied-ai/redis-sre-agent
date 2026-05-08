"""Redis Agent Memory Server integration helpers."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.progress import ProgressEmitter
from redis_sre_agent.core.targets import resolve_binding_subject
from redis_sre_agent.core.turn_scope import TurnScope

logger = logging.getLogger(__name__)

SKIP_MEMORY_USER_IDS = {"", "unknown", "system", "mcp-user", "scheduler"}

try:
    from agent_memory_client import MemoryAPIClient, MemoryClientConfig
    from agent_memory_client.filters import Entities, Namespace, UserId
    from agent_memory_client.models import MemoryMessage, MemoryStrategyConfig, WorkingMemory
except ImportError:  # pragma: no cover - exercised only when dependency is absent

    class _Shim:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    MemoryAPIClient = None  # type: ignore[assignment]
    MemoryClientConfig = _Shim  # type: ignore[assignment]
    Entities = _Shim  # type: ignore[assignment]
    Namespace = _Shim  # type: ignore[assignment]
    UserId = _Shim  # type: ignore[assignment]
    MemoryMessage = _Shim  # type: ignore[assignment]
    MemoryStrategyConfig = _Shim  # type: ignore[assignment]
    WorkingMemory = _Shim  # type: ignore[assignment]


DEFAULT_CUSTOM_PROMPT = """Extract only durable user-scoped Redis SRE memory.

Persist only:
- explicit user preferences
- reporting preferences
- user-specific workflow habits
- durable operating style

Do not persist:
- asset incidents
- asset configuration or environment facts
- ownership or inventory facts
- request narration
- raw transcripts, logs, tool outputs, or secrets

If content is mixed or ambiguous, do not persist it.

Current datetime: {current_datetime}
Conversation: {message}"""

ASSET_CUSTOM_PROMPT = """Extract only durable shared operational memory about the Redis asset.

Persist only:
- asset incidents and outcomes
- configuration or environment facts
- recurring operational context that will matter in future troubleshooting

Do not persist:
- user preferences
- workflow habits
- request narration
- raw transcripts, logs, tool outputs, or secrets

If content is mixed or ambiguous, do not persist it.

Current datetime: {current_datetime}
Conversation: {message}"""


@dataclass
class TurnMemoryContext:
    """Prepared memory context for a single agent turn."""

    system_prompt: Optional[str]
    user_working_memory: Any = None
    asset_working_memory: Any = None
    long_term_count: int = 0
    status: str = "disabled"
    error: Optional[str] = None


@dataclass
class PreparedAgentTurnMemory:
    """Prepared AMS state for a single agent turn."""

    memory_service: "AgentMemoryService"
    memory_context: TurnMemoryContext
    session_id: str
    user_id: Optional[str]
    query: str
    instance_id: Optional[str]
    cluster_id: Optional[str]
    emitter: Optional[ProgressEmitter] = None

    async def persist_response_fail_open(self, assistant_message: str) -> None:
        """Persist turn memory without interrupting the user-visible response path."""

        try:
            await self.memory_service.persist_turn(
                session_id=self.session_id,
                user_id=self.user_id,
                user_message=self.query,
                assistant_message=assistant_message,
                user_working_memory=self.memory_context.user_working_memory,
                asset_working_memory=self.memory_context.asset_working_memory,
                instance_id=self.instance_id,
                cluster_id=self.cluster_id,
                thread_id=self.session_id,
                emitter=self.emitter,
            )
        except Exception:
            logger.exception(
                "Failed to persist memory for session %s; returning response without memory update",
                self.session_id,
            )


class AgentMemoryService:
    """Thin AMS adapter for turn-scoped retrieval and persistence."""

    _PREFERENCE_PATTERNS = (
        "prefer",
        "preference",
        "likes ",
        "wants ",
        "interactive session",
        "interactive workflow",
        "executive-summary-first",
        "exec-summary-first",
        "top-line risk",
        "metrics-first",
        "metric-heavy",
        "root-cause-first",
        "remediation-first",
        "explanation-first",
        "summary-first",
    )
    _ASSET_PATTERNS = (
        "redis",
        "instance",
        "cluster",
        "service-",
        "latency",
        "backup",
        "failover",
        "replica",
        "replication",
        "oom",
        "out of memory",
        "incident",
        "config",
        "configuration",
        "environment",
        "production",
        "development",
        "memory",
        "cpu",
        "shard",
        "cache",
        "error",
    )
    _MIXED_SPLIT_MARKERS = (" when ", " while ", " during ", " after ", " before ")

    def __init__(self) -> None:
        self._enabled = bool(settings.agent_memory_enabled and settings.agent_memory_base_url)

    @property
    def enabled(self) -> bool:
        return self._enabled and MemoryAPIClient is not None

    def _config(self) -> Any:
        if not self.enabled:
            raise RuntimeError("Agent memory is not enabled")
        return MemoryClientConfig(
            base_url=settings.agent_memory_base_url or "",
            timeout=settings.agent_memory_timeout,
            default_namespace=settings.agent_memory_namespace,
            default_model_name=settings.agent_memory_model_name,
        )

    def _strategy(self) -> Any:
        prompt = settings.agent_memory_custom_prompt or DEFAULT_CUSTOM_PROMPT
        return MemoryStrategyConfig(
            strategy="custom",
            config={"custom_prompt": prompt},
        )

    @staticmethod
    def _asset_strategy() -> Any:
        return MemoryStrategyConfig(
            strategy="custom",
            config={"custom_prompt": ASSET_CUSTOM_PROMPT},
        )

    @classmethod
    def _is_operator_preference_memory(cls, text: Optional[str]) -> bool:
        if not text:
            return False
        lowered = text.lower()
        return any(marker in lowered for marker in cls._PREFERENCE_PATTERNS)

    @classmethod
    def _contains_asset_signal(cls, text: Optional[str]) -> bool:
        if not text:
            return False
        lowered = text.lower()
        return any(marker in lowered for marker in cls._ASSET_PATTERNS)

    @staticmethod
    def _split_sentences(text: Optional[str]) -> List[str]:
        if not text:
            return []
        normalized = re.sub(r"\s+", " ", text.strip())
        if not normalized:
            return []
        parts = re.split(r"(?<=[.!?])\s+", normalized)
        return [part.strip() for part in parts if part.strip()]

    @classmethod
    def _scope_messages(
        cls,
        *,
        user_message: str,
        assistant_message: str,
        include_user_scope: bool,
        include_asset_scope: bool,
    ) -> Dict[str, Dict[str, List[str]]]:
        scoped: Dict[str, Dict[str, List[str]]] = {
            "user": {"user": [], "assistant": []},
            "asset": {"user": [], "assistant": []},
        }

        def _split_mixed_sentence(sentence: str) -> tuple[Optional[str], Optional[str]]:
            lowered = sentence.lower()
            for marker in cls._MIXED_SPLIT_MARKERS:
                if marker not in lowered:
                    continue
                index = lowered.index(marker)
                user_fragment = sentence[:index].strip(" ,.")
                asset_fragment = sentence[index + len(marker) :].strip(" ,.")
                if not user_fragment or not asset_fragment:
                    continue
                if not cls._is_operator_preference_memory(user_fragment):
                    continue
                if not cls._contains_asset_signal(asset_fragment):
                    continue
                return user_fragment, asset_fragment
            return None, None

        def _classify(sentences: List[str], role: str) -> None:
            for sentence in sentences:
                is_user = include_user_scope and cls._is_operator_preference_memory(sentence)
                is_asset = include_asset_scope and cls._contains_asset_signal(sentence)

                if is_user and is_asset:
                    user_fragment, asset_fragment = _split_mixed_sentence(sentence)
                    if user_fragment and asset_fragment:
                        scoped["user"][role].append(user_fragment)
                        scoped["asset"][role].append(asset_fragment)
                    continue

                if is_user:
                    scoped["user"][role].append(sentence)
                    continue
                if is_asset:
                    scoped["asset"][role].append(sentence)

        _classify(cls._split_sentences(user_message), "user")
        _classify(cls._split_sentences(assistant_message), "assistant")
        return scoped

    @classmethod
    def _filter_asset_memories(cls, memories: List[Any]) -> List[Any]:
        return [
            memory
            for memory in memories
            if not cls._is_operator_preference_memory(getattr(memory, "text", None))
        ]

    @staticmethod
    def _target_entities(
        instance_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
    ) -> List[str]:
        entities: List[str] = []
        if instance_id:
            entities.append(f"instance:{instance_id}")
        if cluster_id:
            entities.append(f"cluster:{cluster_id}")
        return entities

    @classmethod
    def _valid_user_id(cls, user_id: Optional[str]) -> bool:
        return bool(user_id and user_id not in SKIP_MEMORY_USER_IDS)

    @classmethod
    def _asset_session_id(
        cls,
        instance_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
    ) -> Optional[str]:
        if instance_id:
            return f"asset:instance:{instance_id}"
        if cluster_id:
            return f"asset:cluster:{cluster_id}"
        return None

    @staticmethod
    def _format_memory_prompt(
        sections: List[tuple[str, Any, List[Any], bool]],
    ) -> Optional[str]:
        rendered_sections: List[str] = []

        for label, working_memory, memories, include_working_context in sections:
            parts: List[str] = []
            context = (
                getattr(working_memory, "context", None)
                if include_working_context and working_memory is not None
                else None
            )
            if context:
                parts.append(f"Working memory summary:\n{context}")

            if memories:
                rendered = []
                for memory in memories:
                    text = getattr(memory, "text", None)
                    if not text:
                        continue
                    memory_type = getattr(memory, "memory_type", None)
                    prefix = f"[{memory_type}] " if memory_type else ""
                    rendered.append(f"- {prefix}{text}")
                if rendered:
                    parts.append("Relevant long-term memories:\n" + "\n".join(rendered))

            if parts:
                rendered_sections.append(f"{label}\n" + "\n\n".join(parts))

        if not rendered_sections:
            return None

        return "MEMORY CONTEXT (prior context only; verify current state with live tools)\n" + (
            "\n\n".join(rendered_sections)
        )

    @staticmethod
    async def _emit(
        emitter: Optional[ProgressEmitter],
        message: str,
        update_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if emitter is None:
            return
        try:
            await emitter.emit(message, update_type, metadata)
        except Exception as exc:  # pragma: no cover - best effort only
            logger.warning("Failed to emit agent-memory progress update: %s", exc)

    async def prepare_turn_context(
        self,
        *,
        query: str,
        session_id: str,
        user_id: Optional[str],
        instance_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
        emitter: Optional[ProgressEmitter] = None,
    ) -> TurnMemoryContext:
        """Load working memory and relevant long-term memories for a turn."""

        if not self._enabled:
            return TurnMemoryContext(system_prompt=None, status="disabled")
        if MemoryAPIClient is None:
            msg = "agent-memory-client dependency is unavailable"
            await self._emit(emitter, msg, "memory_unavailable")
            return TurnMemoryContext(system_prompt=None, status="unavailable", error=msg)

        user_scope = self._valid_user_id(user_id)
        entities = self._target_entities(instance_id=instance_id, cluster_id=cluster_id)
        asset_scope = bool(entities)
        if not user_scope and not asset_scope:
            return TurnMemoryContext(system_prompt=None, status="missing_scope")

        try:
            async with MemoryAPIClient(self._config()) as client:
                prompt_sections: List[tuple[str, Any, List[Any], bool]] = []
                total_memories = 0
                user_working_memory = None
                asset_working_memory = None
                created_any = False

                if user_scope:
                    created, user_working_memory = await client.get_or_create_working_memory(
                        session_id=session_id,
                        user_id=user_id,
                        namespace=settings.agent_memory_namespace,
                        model_name=settings.agent_memory_model_name,
                        long_term_memory_strategy=self._strategy(),
                    )
                    user_memories_result = await client.search_long_term_memory(
                        text=query,
                        user_id=UserId(eq=user_id),
                        namespace=Namespace(eq=settings.agent_memory_namespace),
                        limit=settings.agent_memory_retrieval_limit,
                    )
                    user_memories = list(getattr(user_memories_result, "memories", []) or [])
                    prompt_sections.append(
                        ("User-scoped memory", user_working_memory, user_memories, True)
                    )
                    total_memories += len(user_memories)
                    created_any = created_any or created

                if asset_scope:
                    asset_session_id = (
                        self._asset_session_id(
                            instance_id=instance_id,
                            cluster_id=cluster_id,
                        )
                        or session_id
                    )
                    created, asset_working_memory = await client.get_or_create_working_memory(
                        session_id=asset_session_id,
                        namespace=settings.agent_memory_asset_namespace,
                        model_name=settings.agent_memory_model_name,
                        long_term_memory_strategy=self._asset_strategy(),
                    )
                    asset_memories_result = await client.search_long_term_memory(
                        text=query,
                        namespace=Namespace(eq=settings.agent_memory_asset_namespace),
                        entities=Entities(any=entities),
                        limit=settings.agent_memory_retrieval_limit,
                    )
                    asset_memories = self._filter_asset_memories(
                        list(getattr(asset_memories_result, "memories", []) or [])
                    )
                    prompt_sections.append(
                        ("Asset-scoped memory", asset_working_memory, asset_memories, False)
                    )
                    total_memories += len(asset_memories)
                    created_any = created_any or created

                await self._emit(
                    emitter,
                    (
                        f"Loaded {total_memories} AMS memories"
                        if total_memories
                        else "No relevant AMS memories found"
                    ),
                    "memory_context",
                    {
                        "status": "created" if created_any else "loaded",
                        "long_term_count": total_memories,
                        "user_scope": user_scope,
                        "asset_scope": asset_scope,
                        "session_id": session_id,
                    },
                )
                return TurnMemoryContext(
                    system_prompt=self._format_memory_prompt(prompt_sections),
                    user_working_memory=user_working_memory,
                    asset_working_memory=asset_working_memory,
                    long_term_count=total_memories,
                    status="loaded",
                )
        except Exception as exc:
            logger.warning("AMS retrieval failed for session %s: %s", session_id, exc)
            await self._emit(
                emitter,
                "AMS retrieval failed; continuing without memory context",
                "memory_error",
                {"stage": "retrieve", "error": str(exc), "session_id": session_id},
            )
            return TurnMemoryContext(system_prompt=None, status="error", error=str(exc))

    async def persist_turn(
        self,
        *,
        session_id: str,
        user_id: Optional[str],
        user_message: str,
        assistant_message: str,
        user_working_memory: Any = None,
        asset_working_memory: Any = None,
        instance_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        emitter: Optional[ProgressEmitter] = None,
    ) -> None:
        """Persist the latest turn into AMS working memory."""

        if not self.enabled:
            return

        user_scope = self._valid_user_id(user_id)
        entities = self._target_entities(instance_id=instance_id, cluster_id=cluster_id)
        asset_scope = bool(entities)
        if not user_scope and not asset_scope:
            return

        try:
            async with MemoryAPIClient(self._config()) as client:
                turn_timestamp = datetime.now(timezone.utc)
                recent_limit = max(2, int(settings.agent_memory_recent_message_limit))

                scoped_payloads = self._scope_messages(
                    user_message=user_message,
                    assistant_message=assistant_message,
                    include_user_scope=user_scope,
                    include_asset_scope=asset_scope,
                )

                async def _put_memory(
                    *,
                    namespace: str,
                    scope_session_id: str,
                    scope_user_id: Optional[str],
                    working_memory: Any,
                    strategy: Any,
                    include_user_label: bool,
                ) -> None:
                    nonlocal client

                    scope_key = "user" if scope_user_id is not None else "asset"
                    scoped_user_text = "\n".join(scoped_payloads[scope_key]["user"]).strip()
                    scoped_assistant_text = "\n".join(scoped_payloads[scope_key]["assistant"]).strip()
                    if not scoped_user_text and not scoped_assistant_text:
                        return

                    if working_memory is None:
                        kwargs: Dict[str, Any] = {
                            "session_id": scope_session_id,
                            "namespace": namespace,
                            "model_name": settings.agent_memory_model_name,
                            "long_term_memory_strategy": strategy,
                        }
                        if scope_user_id is not None:
                            kwargs["user_id"] = scope_user_id
                        _, working_memory = await client.get_or_create_working_memory(**kwargs)

                    existing_messages = list(getattr(working_memory, "messages", []) or [])
                    if scoped_user_text:
                        existing_messages.append(
                            MemoryMessage(
                                role="user",
                                content=scoped_user_text,
                                created_at=turn_timestamp,
                            )
                        )
                    if scoped_assistant_text:
                        existing_messages.append(
                            MemoryMessage(
                                role="assistant",
                                content=scoped_assistant_text,
                                created_at=turn_timestamp,
                            )
                        )
                    trimmed_messages = existing_messages[-recent_limit:]

                    target_context = []
                    if instance_id:
                        target_context.append(f"Target instance: {instance_id}")
                    if cluster_id:
                        target_context.append(f"Target cluster: {cluster_id}")
                    if thread_id:
                        target_context.append(f"Thread ID: {thread_id}")
                    if include_user_label and scope_user_id:
                        target_context.append(f"User ID: {scope_user_id}")

                    existing_data = dict(getattr(working_memory, "data", None) or {})
                    turn_data = {
                        "thread_id": thread_id or session_id,
                        "user_id": scope_user_id,
                        "instance_id": instance_id,
                        "cluster_id": cluster_id,
                        "last_turn_at": turn_timestamp.isoformat(),
                    }
                    existing_data.update(
                        {key: value for key, value in turn_data.items() if value is not None}
                    )
                    existing_context = getattr(working_memory, "context", None)
                    combined_context_parts = list(target_context)
                    if existing_context:
                        for context_line in existing_context.splitlines():
                            if context_line and context_line not in combined_context_parts:
                                combined_context_parts.append(context_line)

                    updated_memory = WorkingMemory(
                        session_id=scope_session_id,
                        namespace=namespace,
                        user_id=scope_user_id,
                        messages=trimmed_messages,
                        memories=list(getattr(working_memory, "memories", []) or []),
                        data=existing_data,
                        context="\n".join(combined_context_parts)
                        if combined_context_parts
                        else None,
                        long_term_memory_strategy=strategy,
                        ttl_seconds=settings.agent_memory_working_ttl_seconds,
                    )

                    await client.put_working_memory(
                        scope_session_id,
                        updated_memory,
                        user_id=scope_user_id,
                        model_name=settings.agent_memory_model_name,
                    )

                if user_scope:
                    await _put_memory(
                        namespace=settings.agent_memory_namespace,
                        scope_session_id=session_id,
                        scope_user_id=user_id,
                        working_memory=user_working_memory,
                        strategy=self._strategy(),
                        include_user_label=True,
                    )

                if asset_scope:
                    await _put_memory(
                        namespace=settings.agent_memory_asset_namespace,
                        scope_session_id=self._asset_session_id(
                            instance_id=instance_id,
                            cluster_id=cluster_id,
                        )
                        or session_id,
                        scope_user_id=None,
                        working_memory=asset_working_memory,
                        strategy=self._asset_strategy(),
                        include_user_label=False,
                    )

                await self._emit(
                    emitter,
                    "Persisted turn to AMS working memory",
                    "memory_write",
                    {
                        "session_id": session_id,
                        "thread_id": thread_id or session_id,
                        "user_scope": user_scope,
                        "asset_scope": asset_scope,
                    },
                )
        except Exception as exc:
            logger.warning("AMS persistence failed for session %s: %s", session_id, exc)
            await self._emit(
                emitter,
                "AMS persistence failed; continuing without memory writeback",
                "memory_error",
                {"stage": "persist", "error": str(exc), "session_id": session_id},
            )


async def prepare_agent_turn_memory(
    *,
    query: str,
    session_id: str,
    user_id: Optional[str],
    context: Optional[Dict[str, Any]],
    emitter: Optional[ProgressEmitter],
) -> PreparedAgentTurnMemory:
    """Prepare AMS memory state shared by agent implementations."""

    memory_service = AgentMemoryService()
    normalized_context = context or {}
    serialized_turn_scope = normalized_context.get("turn_scope")
    if isinstance(serialized_turn_scope, dict):
        turn_scope = TurnScope.model_validate(serialized_turn_scope)
    else:
        turn_scope = TurnScope.from_context(
            normalized_context,
            thread_id=normalized_context.get("thread_id"),
            session_id=session_id,
        )

    instance_id = normalized_context.get("instance_id")
    cluster_id = normalized_context.get("cluster_id")
    if not instance_id and turn_scope.single_binding_kind == "instance":
        instance_id = await resolve_binding_subject(turn_scope.single_binding)
    if not cluster_id and turn_scope.single_binding_kind == "cluster":
        cluster_id = await resolve_binding_subject(turn_scope.single_binding)
    memory_context = await memory_service.prepare_turn_context(
        query=query,
        session_id=session_id,
        user_id=user_id,
        instance_id=instance_id,
        cluster_id=cluster_id,
        emitter=emitter,
    )
    return PreparedAgentTurnMemory(
        memory_service=memory_service,
        memory_context=memory_context,
        session_id=session_id,
        user_id=user_id,
        query=query,
        instance_id=instance_id,
        cluster_id=cluster_id,
        emitter=emitter,
    )
