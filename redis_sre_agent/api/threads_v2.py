"""V2 Thread API: CRUD and append-messages.

This API is separate from the legacy combined Tasks/Threads endpoints.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status

from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.thread_state import ThreadManager, ThreadStatus
from redis_sre_agent.models.threads import delete_thread as delete_thread_model
from redis_sre_agent.schemas.threads import (
    Message,
    ThreadAppendMessagesRequest,
    ThreadCreateRequest,
    ThreadResponse,
    ThreadUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/threads", response_model=ThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_thread_v2(req: ThreadCreateRequest) -> ThreadResponse:
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

        state = await tm.get_thread_state(thread_id)
        messages = state.context.get("messages", []) if state else []
        return ThreadResponse(
            thread_id=thread_id,
            status=state.status if state else ThreadStatus.QUEUED,
            messages=[Message(**m) for m in messages] if messages else [],
            action_items=[ai.model_dump() for ai in (state.action_items if state else [])],
            metadata=state.metadata.model_dump() if state else {},
            context=state.context if state else {},
        )
    except Exception as e:
        logger.error(f"Failed to create thread: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threads/{thread_id}", response_model=ThreadResponse)
async def get_thread_v2(thread_id: str) -> ThreadResponse:
    rc = get_redis_client()
    tm = ThreadManager(redis_client=rc)
    state = await tm.get_thread_state(thread_id)
    if not state:
        raise HTTPException(status_code=404, detail="Thread not found")
    messages = state.context.get("messages", [])
    return ThreadResponse(
        thread_id=thread_id,
        status=state.status,
        messages=[Message(**m) for m in messages] if messages else [],
        action_items=[ai.model_dump() for ai in state.action_items],
        metadata=state.metadata.model_dump(),
        context=state.context,
    )


@router.patch("/threads/{thread_id}")
async def update_thread_v2(thread_id: str, req: ThreadUpdateRequest) -> Dict[str, Any]:
    rc = get_redis_client()
    tm = ThreadManager(redis_client=rc)
    state = await tm.get_thread_state(thread_id)
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
async def append_messages_v2(thread_id: str, req: ThreadAppendMessagesRequest):
    rc = get_redis_client()
    tm = ThreadManager(redis_client=rc)
    ok = await tm.append_messages(thread_id, [m.model_dump() for m in req.messages])
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to append messages")
    return None


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread_v2(thread_id: str):
    rc = get_redis_client()
    # Reuse existing deletion logic for consistency
    await delete_thread_model(thread_id=thread_id, redis_client=rc)
    return None
