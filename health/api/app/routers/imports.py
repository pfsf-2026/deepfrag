"""Bulk imports. Apple Health export today; Google Fit / Strava / FHIR bundles later."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile

from .. import apple_health
from ..auth import UserId

router = APIRouter(prefix="/api/import", tags=["import"])


@router.post("/apple-health")
async def import_apple_health(file: UploadFile, user_id: int = UserId) -> dict[str, Any]:
    """Upload export.zip or export.xml from the iPhone Health app."""
    data = await file.read()
    try:
        parsed = apple_health.parse(data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"could not parse export: {e}") from e
    written = apple_health.import_into(user_id, parsed)
    return {**parsed["counts"], "written": written}
