"""Thread API: CRUD and append-messages.

This API is separate from the legacy combined Tasks/Threads endpoints.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status

from redis_sre_agent.api.schemas import (
    Message,
    ThreadAppendMessagesRequest,
    ThreadCreateRequest,
    ThreadResponse,
    ThreadUpdateRequest,
)
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.threads import ThreadManager
from redis_sre_agent.core.threads import delete_thread as delete_thread_model

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/threads")
async def list_threads(
    user_id: Optional[str] = None, limit: int = 50, offset: int = 0
) -> List[Dict[str, Any]]:
    """List threads with optional filtering.

    Returns lightweight summaries from the threads search index, enriched with
    message_count (number of user/assistant messages) for each thread.
    """
    try:
        rc = get_redis_client()
        tm = ThreadManager(redis_client=rc)
        summaries = await tm.list_threads(user_id=user_id, limit=limit, offset=offset)

        # Enrich with message_count for UI display. Be defensive about failures.
        enriched: List[Dict[str, Any]] = []
        for s in summaries or []:
            s_out = dict(s)
            if "message_count" not in s_out:
                try:
                    state = await tm.get_thread(s_out.get("thread_id"))
                    msgs = []
                    if state is not None:
                        ctx = getattr(state, "context", {}) or {}
                        msgs = ctx.get("messages", []) or []
                    # Only count user/assistant messages (exclude tools/system)
                    s_out["message_count"] = sum(
                        1
                        for m in msgs
                        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
                    )
                except Exception:
                    # If we cannot fetch the state, default to 0 rather than failing the list
                    s_out["message_count"] = 0
            enriched.append(s_out)
        return enriched
    except Exception as e:
        logger.error(f"Failed to list threads: {e}")
        raise HTTPException(status_code=500, detail="Failed to list threads")


@router.post("/threads", response_model=ThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_thread(req: ThreadCreateRequest) -> ThreadResponse:
    try:
        rc = get_redis_client()
        tm = ThreadManager(redis_client=rc)

        thread_id = await tm.create_thread(
            user_id=req.user_id,
            session_id=req.session_id,
            initial_context=req.context or {"messages": []},
            tags=req.tags or [],
        )
        if req.subject:
            await tm.update_thread_context(thread_id, {"subject": req.subject})

        # Optionally append initial messages
        if req.messages:
            await tm.append_messages(thread_id, [m.model_dump() for m in req.messages])

        state = await tm.get_thread(thread_id)
        messages = state.context.get("messages", []) if state else []
        # Return created thread state (messages + context)
        return ThreadResponse(
            thread_id=thread_id,
            messages=[Message(**m) for m in messages] if messages else [],
            context=state.context if state else {},
        )
    except Exception as e:
        logger.error(f"Failed to create thread: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threads/{thread_id}", response_model=ThreadResponse)
async def get_thread(thread_id: str) -> ThreadResponse:
    rc = get_redis_client()
    tm = ThreadManager(redis_client=rc)
    state = await tm.get_thread(thread_id)
    if not state:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Extract messages from context if present
    messages = state.context.get("messages", [])

    # Build metadata dict compatible with UI expectations, robust to mocks
    metadata: Optional[Dict[str, Any]] = None
    md_dump = getattr(state.metadata, "model_dump", None)
    if callable(md_dump):
        try:
            metadata = md_dump()
        except Exception:
            metadata = None
    if metadata is None:
        try:
            metadata = dict(state.metadata)  # type: ignore[arg-type]
        except Exception:
            metadata = None

    return ThreadResponse(
        thread_id=thread_id,
        user_id=(metadata.get("user_id") if metadata else None),
        priority=(metadata.get("priority", 0) if metadata else 0),
        tags=(metadata.get("tags", []) if metadata else []),
        subject=(metadata.get("subject") if metadata else None),
        messages=[Message(**m) for m in messages] if messages else [],
        context=getattr(state, "context", {}),
        updates=[u.model_dump() for u in getattr(state, "updates", [])]
        if getattr(state, "updates", None)
        else [],
        result=getattr(state, "result", None),
        error_message=getattr(state, "error_message", None),
        metadata=metadata,
    )


@router.patch("/threads/{thread_id}")
async def update_thread(thread_id: str, req: ThreadUpdateRequest) -> Dict[str, Any]:
    rc = get_redis_client()
    tm = ThreadManager(redis_client=rc)
    state = await tm.get_thread(thread_id)
    if not state:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Update metadata/context minimally
    if req.subject is not None:
        await tm.update_thread_context(thread_id, {"subject": req.subject})
    if req.priority is not None:
        await tm.update_thread_context(thread_id, {"priority": req.priority})
    if req.tags is not None:
        await tm.update_thread_context(thread_id, {"tags": req.tags})
    if req.context is not None:
        await tm.update_thread_context(thread_id, req.context, merge=True)

    return {"updated": True}


@router.post("/threads/{thread_id}/append-messages", status_code=status.HTTP_204_NO_CONTENT)
async def append_messages(thread_id: str, req: ThreadAppendMessagesRequest):
    rc = get_redis_client()
    tm = ThreadManager(redis_client=rc)
    ok = await tm.append_messages(thread_id, [m.model_dump() for m in req.messages])
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to append messages")
    return None


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(thread_id: str):
    rc = get_redis_client()
    # Reuse existing deletion logic for consistency
    await delete_thread_model(thread_id=thread_id, redis_client=rc)
    return None
