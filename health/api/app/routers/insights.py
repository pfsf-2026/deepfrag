"""Today-screen items, and the endpoint a scheduler hits to produce them."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from .. import repo
from ..ai.briefing import run_briefing
from ..auth import UserId
from ..schemas import InsightIn

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("")
def list_insights(include_dismissed: bool = False, user_id: int = UserId) -> list[dict[str, Any]]:
    return repo.list_insights(user_id, include_dismissed=include_dismissed)


@router.post("", status_code=201)
def create_insight(body: InsightIn, user_id: int = UserId) -> dict[str, Any]:
    fields = body.model_dump()
    fields["data"] = {**fields["data"], "source": "manual"}
    return repo.insert_simple("insights", user_id, fields)


@router.post("/{insight_id}/ack")
def ack(insight_id: int, user_id: int = UserId) -> dict[str, Any]:
    row = repo.mark_insight(user_id, insight_id, "acknowledged_at")
    if row is None:
        raise HTTPException(404)
    return row


@router.post("/{insight_id}/dismiss")
def dismiss(insight_id: int, user_id: int = UserId) -> dict[str, Any]:
    row = repo.mark_insight(user_id, insight_id, "dismissed_at")
    if row is None:
        raise HTTPException(404)
    return row


@router.post("/run")
def run(days: int = 14, user_id: int = UserId) -> dict[str, Any]:
    """Generate today's briefing now. Wire a daily scheduler (cron / Cloud Scheduler) to this."""
    return run_briefing(user_id, days=days)
