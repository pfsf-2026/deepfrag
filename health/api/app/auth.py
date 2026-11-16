"""Bearer-token auth, single user for now.

The app sends `Authorization: Bearer <HEALTH_APP_TOKEN>`; a match resolves to
user 1. When HEALTH_APP_TOKEN is unset the API is open and logs a warning once,
which is only acceptable on localhost. Real sign-in (Apple / passkeys) replaces
`current_user` without touching the routers, which only ever see a user_id.
"""
from __future__ import annotations

import hmac
import logging

from fastapi import Depends, HTTPException, Request

from .config import settings

log = logging.getLogger("health.auth")
_warned = False
OWNER_USER_ID = 1


def current_user(request: Request) -> int:
    global _warned
    if settings.app_token is None:
        if not _warned:
            log.warning("HEALTH_APP_TOKEN unset: API is open. Fine on localhost, never in production.")
            _warned = True
        return OWNER_USER_ID
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token, settings.app_token):
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")
    return OWNER_USER_ID


UserId = Depends(current_user)
