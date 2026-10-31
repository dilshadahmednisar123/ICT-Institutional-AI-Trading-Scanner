"""Persistent scan history using the Vercel Blob REST API (private store)."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("ict_scanner.storage")
BLOB_API = "https://blob.vercel-storage.com"

def _token() -> str:
    return os.getenv("BLOB_READ_WRITE_TOKEN", "").strip()

def _headers() -> Dict[str, str]:
    token = _token()
    return {"Authorization": f"Bearer {token}", "x-api-version": "7"}

def _list_blobs(limit: int = 1000) -> List[Dict[str, Any]]:
    response = httpx.get(
        BLOB_API,
        params={"prefix": "signals/", "limit": min(max(limit, 1), 1000)},
        headers=_headers(),
        timeout=20.0,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("blobs", []) if isinstance(payload, dict) else []

def save_scan_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Persist one complete scan as an immutable private JSON blob."""
    if not _token():
        return {"stored": False, "reason": "BLOB_READ_WRITE_TOKEN is not configured"}
    now = datetime.now(timezone.utc)
    pathname = f"signals/{now:%Y/%m/%d/%H%M%S}-{uuid.uuid4().hex}.json"
    payload = {
        "timestamp_utc": now.isoformat(),
        "count": len(results),
        "results": results,
    }
    headers = {
        **_headers(),
        "x-content-type": "application/json",
        "x-add-random-suffix": "0",
        "x-allow-overwrite": "0",
    }
    try:
        response = httpx.put(
            BLOB_API,
            params={"pathname": pathname},
            content=json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8"),
            headers=headers,
            timeout=30.0,
        )
        if response.is_error:
            raise RuntimeError(f"Vercel Blob upload failed ({response.status_code}): {response.text[:500]}")
        blob = response.json()
        return {"stored": True, "pathname": blob.get("pathname", pathname), "url": blob.get("url")}
    except Exception as exc:
        logger.exception("Could not persist scan results")
        return {"stored": False, "reason": f"{type(exc).__name__}: {exc}"}

def get_recent_signals(limit: int = 100, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read recent private scan snapshots and flatten them into signal rows."""
    if not _token():
        return []
    try:
        blobs = _list_blobs()
        blobs.sort(key=lambda item: item.get("uploadedAt") or item.get("pathname", ""), reverse=True)
        output: List[Dict[str, Any]] = []
        for blob in blobs[:50]:
            url = blob.get("url")
            if not url:
                continue
            response = httpx.get(url, headers=_headers(), timeout=20.0)
            response.raise_for_status()
            snapshot = response.json()
            scanned_at = snapshot.get("timestamp_utc")
            for result in snapshot.get("results", []):
                if status and str(result.get("setup_status", "")).upper() != status.upper():
                    continue
                output.append({**result, "scan_timestamp_utc": scanned_at})
                if len(output) >= limit:
                    return output
        return output
    except Exception:
        logger.exception("Could not read persisted scan history")
        return []

def storage_health() -> Dict[str, Any]:
    if not _token():
        return {"available": False, "provider": "Vercel Blob (private)", "reason": "BLOB_READ_WRITE_TOKEN missing"}
    try:
        blobs = _list_blobs(limit=1)
        return {
            "available": True,
            "provider": "Vercel Blob (private)",
            "objects_visible": len(blobs),
        }
    except Exception as exc:
        return {"available": False, "provider": "Vercel Blob (private)", "reason": f"{type(exc).__name__}: {exc}"}
