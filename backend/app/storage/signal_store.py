"""Persistent scan history backed by a private Vercel Blob store."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ict_scanner.storage")

def _has_token() -> bool:
    return bool(os.getenv("BLOB_READ_WRITE_TOKEN", "").strip())

async def _save_async(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    from vercel.blob import AsyncBlobClient
    now = datetime.now(timezone.utc)
    pathname = f"signals/{now:%Y/%m/%d/%H%M%S}-{uuid.uuid4().hex}.json"
    payload = {"timestamp_utc": now.isoformat(), "count": len(results), "results": results}
    async with AsyncBlobClient() as client:
        blob = await client.put(
            pathname,
            json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8"),
            access="private",
            content_type="application/json",
            add_random_suffix=False,
        )
    return {"stored": True, "pathname": blob.pathname, "url": blob.url}

def save_scan_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Persist one complete scan as an immutable private JSON blob."""
    if not _has_token():
        return {"stored": False, "reason": "BLOB_READ_WRITE_TOKEN is not configured"}
    try:
        return asyncio.run(_save_async(results))
    except Exception as exc:
        logger.exception("Could not persist scan results")
        return {"stored": False, "reason": f"{type(exc).__name__}: {exc}"}

async def _get_recent_async(limit: int, status: Optional[str]) -> List[Dict[str, Any]]:
    from vercel.blob import AsyncBlobClient
    output: List[Dict[str, Any]] = []
    async with AsyncBlobClient() as client:
        listed = await client.list_objects(prefix="signals/", limit=1000)
        blobs = list(getattr(listed, "blobs", []) or [])
        blobs.sort(
            key=lambda item: getattr(item, "uploaded_at", None) or getattr(item, "pathname", ""),
            reverse=True,
        )
        for blob in blobs[:50]:
            item = await client.get(blob.pathname, access="private")
            if item is None or item.status_code != 200 or item.stream is None:
                continue
            chunks = [chunk async for chunk in item.stream]
            snapshot = json.loads(b"".join(chunks).decode("utf-8"))
            scanned_at = snapshot.get("timestamp_utc")
            for result in snapshot.get("results", []):
                if status and str(result.get("setup_status", "")).upper() != status.upper():
                    continue
                output.append({**result, "scan_timestamp_utc": scanned_at})
                if len(output) >= limit:
                    return output
    return output

def get_recent_signals(limit: int = 100, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read recent scan snapshots and flatten them into signal rows."""
    if not _has_token():
        return []
    try:
        return asyncio.run(_get_recent_async(limit, status))
    except Exception:
        logger.exception("Could not read persisted scan history")
        return []

async def _storage_health_async() -> Dict[str, Any]:
    from vercel.blob import AsyncBlobClient
    async with AsyncBlobClient() as client:
        listed = await client.list_objects(prefix="signals/", limit=1)
        return {
            "available": True,
            "provider": "Vercel Blob (private)",
            "objects_visible": len(getattr(listed, "blobs", []) or []),
        }

def storage_health() -> Dict[str, Any]:
    if not _has_token():
        return {"available": False, "provider": "Vercel Blob", "reason": "BLOB_READ_WRITE_TOKEN missing"}
    try:
        return asyncio.run(_storage_health_async())
    except Exception as exc:
        return {"available": False, "provider": "Vercel Blob (private)", "reason": f"{type(exc).__name__}: {exc}"}
