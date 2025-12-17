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

        # Enrich with message_count and latest_message for UI display.
        enriched: List[Dict[str, Any]] = []
        for s in summaries or []:
            s_out = dict(s)
            try:
                state = await tm.get_thread(s_out.get("thread_id"))
                if state is not None:
                    # Get messages from the Thread.messages list (primary storage)
                    msgs = state.messages or []
                    # Count user/assistant messages
                    user_assistant_msgs = [m for m in msgs if m.role in ("user", "assistant")]
                    s_out["message_count"] = len(user_assistant_msgs)

                    # Get latest message content from the last assistant or user message
                    if user_assistant_msgs:
                        last_msg = user_assistant_msgs[-1]
                        content = last_msg.content or ""
                        # Truncate for preview
                        s_out["latest_message"] = (
                            content[:100] + "..." if len(content) > 100 else content
                        )
                else:
                    s_out["message_count"] = 0
            except Exception:
                # If we cannot fetch the state, default to 0 rather than failing the list
                if "message_count" not in s_out:
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
            initial_context=req.context or {},
            tags=req.tags or [],
        )
        if req.subject:
            try:
                await tm.set_thread_subject(thread_id, req.subject)
            except Exception:
                # Fallback for mocks/tests that patch update_thread_context only
                await tm.update_thread_context(thread_id, {"subject": req.subject})

        # Optionally append initial messages
        if req.messages:
            await tm.append_messages(thread_id, [m.model_dump() for m in req.messages])

        state = await tm.get_thread(thread_id)
        if not state:
            raise HTTPException(status_code=500, detail="Failed to retrieve created thread")

        # Convert Message objects to API schema
        messages = [
            Message(role=m.role, content=m.content, metadata=m.metadata) for m in state.messages
        ]

        return ThreadResponse(
            thread_id=thread_id,
            messages=messages,
            context=state.context,
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

    # Build metadata dict compatible with UI expectations
    try:
        metadata = state.metadata.model_dump()
    except Exception:
        try:
            metadata = dict(state.metadata)  # type: ignore[arg-type]
        except Exception:
            metadata = None

    # Convert Message objects to API schema
    messages = [
        Message(role=m.role, content=m.content, metadata=m.metadata) for m in state.messages
    ]

    # Fetch the latest task's updates, result, and status for real-time UI display
    updates = []
    result = None
    error_message = None
    task_status = None

    try:
        from redis_sre_agent.core.keys import RedisKeys
        from redis_sre_agent.core.tasks import TaskManager

        task_manager = TaskManager(redis_client=rc)
        # Get the latest task for this thread
        latest_task_ids = await rc.zrevrange(RedisKeys.thread_tasks_index(thread_id), 0, 0)
        if latest_task_ids:
            latest_task_id = latest_task_ids[0]
            if isinstance(latest_task_id, bytes):
                latest_task_id = latest_task_id.decode()
            task_state = await task_manager.get_task_state(latest_task_id)
            if task_state:
                updates = [u.model_dump() for u in (task_state.updates or [])]
                result = task_state.result
                error_message = task_state.error_message
                task_status = task_state.status
    except Exception as e:
        logger.warning(f"Failed to fetch task updates for thread {thread_id}: {e}")

    return ThreadResponse(
        thread_id=thread_id,
        user_id=(metadata.get("user_id") if metadata else None),
        priority=(metadata.get("priority", 0) if metadata else 0),
        tags=(metadata.get("tags", []) if metadata else []),
        subject=(metadata.get("subject") if metadata else None),
        messages=messages,
        context=state.context,
        metadata=metadata,
        updates=updates,
        result=result,
        error_message=error_message,
        status=task_status,
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
        try:
            await tm.set_thread_subject(thread_id, req.subject)
        except Exception:
            # Fallback for mocks/tests that patch update_thread_context only
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
