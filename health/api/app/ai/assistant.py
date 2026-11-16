"""The chat agent: Claude + tools over the owner's record, streamed as SSE.

Each turn:
  1. load the thread's stored messages (raw content arrays, so thinking and tool
     blocks replay unchanged),
  2. append the new user message with the current time,
  3. run the SDK tool runner with stream=True, forwarding text deltas and tool
     activity to the client as they happen,
  4. persist every assistant turn and tool-result turn the runner produced.

SSE event shapes (JSON after `data:`):
  {"type":"thread","thread_id":N}
  {"type":"text","text":"..."}            incremental assistant text
  {"type":"tool","name":"log_meal"}        a tool call started
  {"type":"done","stop_reason":"end_turn"}
  {"type":"error","message":"..."}
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterator

import anthropic

from .. import repo
from ..config import settings
from . import tools as T
from .client import client
from .prompts import ASSISTANT_SYSTEM

log = logging.getLogger("health.assistant")


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _user_turn(text: str, tz: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat(timespec="minutes")
    return {"role": "user", "content": [{"type": "text", "text": f"[now: {now}; owner timezone: {tz}]\n{text}"}]}


def _tool_list(user_id: int) -> list[Any]:
    tools: list[Any] = T.build_tools(user_id)
    if settings.web_search:
        tools.append(T.WEB_SEARCH_TOOL)
    return tools


def stream_reply(user_id: int, thread_id: int | None, message: str) -> Iterator[str]:
    try:
        profile = repo.get_profile(user_id)
        if thread_id is None or repo.get_thread(user_id, thread_id) is None:
            thread = repo.create_thread(user_id, title=message[:80])
            thread_id = int(thread["id"])
        yield _sse({"type": "thread", "thread_id": thread_id})

        history = [{"role": m["role"], "content": m["content"]} for m in repo.thread_messages(thread_id)]
        user_msg = _user_turn(message, profile.get("timezone") or "UTC")
        repo.append_message(thread_id, "user", user_msg["content"])
        messages = [*history, user_msg]

        runner = client().beta.messages.tool_runner(
            model=settings.model,
            max_tokens=16000,
            system=[{"type": "text", "text": ASSISTANT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            tools=_tool_list(user_id),
            messages=messages,
            max_iterations=12,
            stream=True,
        )
        stop_reason = None
        for stream in runner:
            with stream:
                for event in stream:
                    if event.type == "text":
                        yield _sse({"type": "text", "text": event.text})
                    elif event.type == "content_block_start" and event.content_block.type == "tool_use":
                        yield _sse({"type": "tool", "name": event.content_block.name})
                final = stream.get_final_message()
            stop_reason = final.stop_reason
            repo.append_message(thread_id, "assistant", [b.model_dump(mode="json", exclude_none=True) for b in final.content])
            if stop_reason in ("max_tokens", "refusal"):
                break
            tool_turn = runner.generate_tool_call_response()
            if tool_turn is not None:
                repo.append_message(thread_id, "user", _plain(tool_turn["content"]))
        yield _sse({"type": "done", "stop_reason": stop_reason})
    except anthropic.AuthenticationError:
        yield _sse({"type": "error", "message": "The server has no Anthropic API key (set ANTHROPIC_API_KEY)."})
    except anthropic.RateLimitError:
        yield _sse({"type": "error", "message": "Rate limited by the model API; try again in a minute."})
    except anthropic.APIStatusError as e:
        log.exception("model API error")
        yield _sse({"type": "error", "message": f"Model API error {e.status_code}: {e.message}"})
    except anthropic.APIConnectionError:
        yield _sse({"type": "error", "message": "Could not reach the model API."})
    except TypeError as e:
        # The SDK raises TypeError when it finds no credentials at all.
        if "authentication method" in str(e):
            yield _sse({"type": "error", "message": "The server has no Anthropic credentials (set ANTHROPIC_API_KEY)."})
        else:
            log.exception("assistant turn failed")
            yield _sse({"type": "error", "message": f"{type(e).__name__}: {e}"})
    except Exception as e:  # noqa: BLE001 - surface anything else to the client, log it here
        log.exception("assistant turn failed")
        yield _sse({"type": "error", "message": f"{type(e).__name__}: {e}"})


def _plain(content: Any) -> Any:
    """Tool-result content from the SDK may contain pydantic params; make it JSON-safe."""
    if hasattr(content, "model_dump"):
        return content.model_dump(mode="json", exclude_none=True)
    if isinstance(content, list):
        return [_plain(c) for c in content]
    if isinstance(content, dict):
        return {k: _plain(v) for k, v in content.items()}
    return content
