"""Assistant chat: POST a message, receive Server-Sent Events."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .. import repo
from ..ai.assistant import stream_reply
from ..auth import UserId
from ..schemas import ChatIn

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/threads")
def list_threads(user_id: int = UserId) -> list[dict[str, Any]]:
    return repo.list_threads(user_id)


@router.get("/threads/{thread_id}")
def get_thread(thread_id: int, user_id: int = UserId) -> dict[str, Any]:
    thread = repo.get_thread(user_id, thread_id)
    if thread is None:
        raise HTTPException(404)
    messages = []
    for m in repo.thread_messages(thread_id):
        # Flatten to what a UI shows: text blocks only, tool traffic hidden.
        text = "".join(b.get("text", "") for b in m["content"] if isinstance(b, dict) and b.get("type") == "text")
        if m["role"] == "user":
            text = text.split("\n", 1)[1] if text.startswith("[now:") and "\n" in text else text
        if text.strip():
            messages.append({"id": m["id"], "role": m["role"], "text": text, "created_at": m["created_at"]})
    return {**thread, "messages": messages}


@router.post("")
def chat(body: ChatIn, user_id: int = UserId) -> StreamingResponse:
    if not body.message.strip():
        raise HTTPException(422, "empty message")
    return StreamingResponse(
        stream_reply(user_id, body.thread_id, body.message.strip()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
