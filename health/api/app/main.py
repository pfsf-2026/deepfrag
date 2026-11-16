"""Health API. Run: uvicorn app.main:app --reload --port 8000"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .config import settings
from .routers import chat, documents, imports, insights, records

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.migrate()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    yield
    db.close_pool()


app = FastAPI(title="Health", version="0.1.0", lifespan=lifespan)

# The Expo web app runs on another origin in dev (localhost:8081); native apps send no Origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("HEALTH_CORS_ORIGINS", "http://localhost:8081,http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (records.router, documents.router, chat.router, insights.router, imports.router):
    app.include_router(r)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    with db.conn() as c:
        c.execute("SELECT 1")
    return {"status": "ok", "model": settings.model}
