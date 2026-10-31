"""Persistent scan history backed by a private Vercel Blob store."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ict_scanner.storage")

def _client():
    if not os.getenv("BLOB_READ_WRITE_TOKEN", "").strip():
        return None
    from vercel.blob import BlobClient
    return BlobClient()

def save_scan_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Persist one complete scan as an immutable private JSON blob."""
    client = _client()
    if client is None:
        return {"stored": False, "reason": "BLOB_READ_WRITE_TOKEN is not configured"}
    now = datetime.now(timezone.utc)
    pathname = f"signals/{now:%Y/%m/%d/%H%M%S}-{uuid.uuid4().hex}.json"
    payload = {
        "timestamp_utc": now.isoformat(),
        "count": len(results),
        "results": results,
    }
    try:
        blob = client.put(
            pathname,
            json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8"),
            access="private",
            content_type="application/json",
            add_random_suffix=False,
        )
        return {"stored": True, "pathname": blob.pathname, "url": blob.url}
    except Exception as exc:
        logger.exception("Could not persist scan results")
        return {"stored": False, "reason": f"{type(exc).__name__}: {exc}"}

def get_recent_signals(limit: int = 100, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read recent scan snapshots and flatten them into signal rows."""
    client = _client()
    if client is None:
        return []
    try:
        listed = client.list_objects(prefix="signals/", limit=1000)
        blobs = list(getattr(listed, "blobs", []) or [])
        blobs.sort(
            key=lambda item: getattr(item, "uploaded_at", None) or getattr(item, "pathname", ""),
            reverse=True,
        )
        output: List[Dict[str, Any]] = []
        for blob in blobs[:50]:
            item = client.get(blob.pathname, access="private")
            if item is None or item.status_code != 200 or item.stream is None:
                continue
            raw = b"".join(item.stream)
            snapshot = json.loads(raw.decode("utf-8"))
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
    client = _client()
    if client is None:
        return {"available": False, "provider": "Vercel Blob", "reason": "BLOB_READ_WRITE_TOKEN missing"}
    try:
        listed = client.list_objects(prefix="signals/", limit=1)
        return {
            "available": True,
            "provider": "Vercel Blob (private)",
            "objects_visible": len(getattr(listed, "blobs", []) or []),
        }
    except Exception as exc:
        return {"available": False, "provider": "Vercel Blob (private)", "reason": f"{type(exc).__name__}: {exc}"}
