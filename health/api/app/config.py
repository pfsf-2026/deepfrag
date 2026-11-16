"""Settings, read from environment variables on access. Nothing secret is committed.

  HEALTH_PG_URL         postgresql://user:pw@host:5432/health   (required)
  HEALTH_APP_TOKEN      shared bearer token the app sends; unset = open (dev only)
  HEALTH_DATA_DIR       where uploaded documents are stored (default ./data)
  HEALTH_MODEL          Claude model for the assistant and briefing (default claude-opus-5-5)
  HEALTH_FAST_MODEL     model for document extraction (default: same as HEALTH_MODEL)
  HEALTH_WEB_SEARCH     "1" lets the assistant use Anthropic's web_search tool (default 1)
  HEALTH_CORS_ORIGINS   comma-separated web origins (default localhost dev ports)
  ANTHROPIC_API_KEY     read by the SDK itself
"""
from __future__ import annotations

import os
from pathlib import Path


class Settings:
    @property
    def pg_url(self) -> str:
        return os.environ.get("HEALTH_PG_URL", "")

    @property
    def app_token(self) -> str | None:
        return os.environ.get("HEALTH_APP_TOKEN") or None

    @property
    def data_dir(self) -> Path:
        return Path(os.environ.get("HEALTH_DATA_DIR", "./data")).resolve()

    @property
    def model(self) -> str:
        return os.environ.get("HEALTH_MODEL", "claude-opus-5-5")

    @property
    def fast_model(self) -> str:
        return os.environ.get("HEALTH_FAST_MODEL") or self.model

    @property
    def web_search(self) -> bool:
        return os.environ.get("HEALTH_WEB_SEARCH", "1") == "1"

    @property
    def pool_min(self) -> int:
        return int(os.environ.get("PG_POOL_MIN", "1"))

    @property
    def pool_max(self) -> int:
        return int(os.environ.get("PG_POOL_MAX", "4"))

    def require_pg(self) -> str:
        if not self.pg_url:
            raise RuntimeError("HEALTH_PG_URL is not set (e.g. postgresql://postgres:postgres@localhost:5432/health)")
        return self.pg_url


settings = Settings()
