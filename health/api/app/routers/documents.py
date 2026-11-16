"""Upload medical documents; extraction runs in the background after the upload returns."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import repo
from ..ai.ingest import process_document
from ..auth import UserId
from ..config import settings

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED = {"application/pdf", "image/jpeg", "image/png", "image/webp", "image/heic", "text/plain"}
MAX_BYTES = 30 * 1024 * 1024


def _safe_name(name: str) -> str:
    name = Path(name or "upload").name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120] or "upload"


@router.get("")
def list_documents(user_id: int = UserId) -> list[dict[str, Any]]:
    rows = repo.list_simple("documents", user_id, order="document_date DESC NULLS LAST, uploaded_at DESC")
    for r in rows:
        r.pop("extracted", None)
        r.pop("storage_key", None)
    return rows


@router.post("", status_code=201)
async def upload_document(file: UploadFile, background: BackgroundTasks, user_id: int = UserId) -> dict[str, Any]:
    media_type = (file.content_type or "").split(";")[0].strip().lower()
    if media_type not in ALLOWED:
        raise HTTPException(415, f"unsupported type {media_type!r}; send PDF, JPEG, PNG, WebP or plain text")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "file over 30 MB")
    digest = hashlib.sha256(data).hexdigest()
    rel = Path("documents") / str(user_id) / f"{digest[:16]}_{_safe_name(file.filename or '')}"
    dest = settings.data_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    row = repo.insert_document(
        user_id, filename=_safe_name(file.filename or ""), media_type=media_type, storage_key=str(rel),
        sha256=digest, size_bytes=len(data),
    )
    if row.pop("inserted", True) or row["status"] in ("pending", "failed"):
        background.add_task(process_document, user_id, int(row["id"]))
    row.pop("extracted", None)
    row.pop("storage_key", None)
    return row


@router.get("/{doc_id}")
def get_document(doc_id: int, user_id: int = UserId) -> dict[str, Any]:
    row = repo.get_row("documents", doc_id, user_id)
    if row is None:
        raise HTTPException(404)
    row.pop("storage_key", None)
    return row


@router.get("/{doc_id}/file")
def download_document(doc_id: int, user_id: int = UserId) -> FileResponse:
    row = repo.get_row("documents", doc_id, user_id)
    if row is None:
        raise HTTPException(404)
    return FileResponse(settings.data_dir / row["storage_key"], media_type=row["media_type"], filename=row["filename"])


@router.post("/{doc_id}/reprocess", status_code=202)
def reprocess(doc_id: int, background: BackgroundTasks, user_id: int = UserId) -> dict[str, Any]:
    if repo.get_row("documents", doc_id, user_id) is None:
        raise HTTPException(404)
    background.add_task(process_document, user_id, doc_id)
    return {"status": "queued"}


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: int, user_id: int = UserId) -> None:
    row = repo.get_row("documents", doc_id, user_id)
    if row is None:
        raise HTTPException(404)
    repo.delete_row("documents", doc_id, user_id)
    try:
        (settings.data_dir / row["storage_key"]).unlink(missing_ok=True)
    except OSError:
        pass
