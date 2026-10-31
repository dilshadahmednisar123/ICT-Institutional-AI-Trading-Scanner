"""
Simple API-key authentication for production hardening.

If API_SECRET_KEY is unset, auth is disabled (local/dev mode).
If set, requests must include header: X-API-Key: <key>

Never embed this key in mobile/frontend production builds for public apps;
prefer server-side BFF or user login later.
"""

from __future__ import annotations
import os
from fastapi import Header, HTTPException, status
from typing import Optional


def api_key_enabled() -> bool:
    return bool(os.getenv("API_SECRET_KEY", "").strip())


async def require_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> None:
    expected = os.getenv("API_SECRET_KEY", "").strip()
    if not expected:
        return  # auth disabled
    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
        )
