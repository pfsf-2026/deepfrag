"""The proactive layer. `run_briefing` builds a compact snapshot of the owner's
recent data, asks Claude for a short list of typed insights, and stores them.
Run it from a scheduler once a day (and after a big import)."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from .. import repo
from ..config import settings
from .client import client
from .prompts import BRIEFING_SYSTEM

log = logging.getLogger("health.briefing")


class Insight(BaseModel):
    kind: Literal["briefing", "nudge", "anomaly", "anticipation", "reminder", "question"]
    severity: Literal["info", "attention", "urgent"]
    title: str
    body: str
    due_at: str | None = Field(description="ISO 8601 datetime for reminders, else null")
    evidence: list[str] = Field(description="the specific numbers or records this rests on")


class Briefing(BaseModel):
    items: list[Insight]


def _default(o: Any) -> Any:
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    return str(o)


def snapshot(user_id: int, days: int = 14) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    latest = repo.latest_observations(user_id)
    kinds = sorted({r["kind"] for r in latest})
    summaries = {k: repo.summarize_observations(user_id, k, since) for k in kinds}
    for s in summaries.values():
        s["daily"] = s["daily"][-days:]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "window_days": days,
        "profile": repo.get_profile(user_id),
        "latest_readings": latest,
        "summaries": summaries,
        "meals": repo.list_meals(user_id, since, limit=200),
        "workouts": repo.list_workouts(user_id, since, limit=100),
        "medications": repo.list_medications(user_id, active_only=True),
        "conditions": repo.list_simple("conditions", user_id, order="created_at DESC"),
        "allergies": repo.list_simple("allergies", user_id, order="substance"),
        "encounters": repo.list_simple("encounters", user_id, order="occurred_at DESC", limit=20),
        "recent_documents": repo.list_simple("documents", user_id, order="uploaded_at DESC", limit=10),
        "open_insights": repo.list_insights(user_id),
    }


def run_briefing(user_id: int, days: int = 14) -> dict[str, Any]:
    snap = snapshot(user_id, days)
    for d in snap["recent_documents"]:
        d.pop("extracted", None); d.pop("storage_key", None)
    response = client().messages.parse(
        model=settings.model,
        max_tokens=16000,
        system=[{"type": "text", "text": BRIEFING_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": "Snapshot:\n" + json.dumps(snap, default=_default)}],
        output_format=Briefing,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError("briefing not produced")
    run_id = uuid.uuid4().hex[:12]
    written = []
    for item in response.parsed_output.items:
        due = None
        if item.due_at:
            try:
                due = datetime.fromisoformat(item.due_at.replace("Z", "+00:00"))
            except ValueError:
                due = None
        row = repo.insert_simple("insights", user_id, {
            "kind": item.kind, "severity": item.severity, "title": item.title[:120], "body": item.body[:2000],
            "due_at": due, "data": {"evidence": item.evidence}, "run_id": run_id,
        })
        written.append(row)
    log.info("briefing %s wrote %d insights for user %s", run_id, len(written), user_id)
    return {"run_id": run_id, "insights": written, "usage": response.usage.model_dump()}
