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
BLOB_API = "https://vercel.com/api/blob"
BLOB_API_VERSION = "12"


def _token() -> str:
    return os.getenv("BLOB_READ_WRITE_TOKEN", "").strip()


def _store_id(token: str) -> str:
    # Vercel read/write tokens use: vercel_blob_rw_<storeId>_<secret>
    parts = token.split("_")
    if len(parts) < 5 or parts[0:3] != ["vercel", "blob", "rw"] or not parts[3]:
        raise ValueError("BLOB_READ_WRITE_TOKEN is not a valid Vercel Blob read/write token")
    return parts[3].removeprefix("store_")


def _headers() -> Dict[str, str]:
    token = _token()
    if not token:
        raise RuntimeError("BLOB_READ_WRITE_TOKEN is not configured")
    return {
        "Authorization": f"Bearer {token}",
        "x-api-version": BLOB_API_VERSION,
        "x-vercel-blob-store-id": _store_id(token),
        "x-api-blob-request-id": str(uuid.uuid4()),
        "x-api-blob-request-attempt": "0",
    }


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
        "x-vercel-blob-access": "private",
        "x-add-random-suffix": "0",
        "x-allow-overwrite": "0",
    }
    try:
        # The official Blob SDK issues PUT to /api/blob/?pathname=<path>.
        # Keep the trailing slash: the route is distinct from the list endpoint.
        response = httpx.put(
            f"{BLOB_API}/",
            params={"pathname": pathname},
            content=json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8"),
            headers=headers,
            timeout=30.0,
        )
        if response.is_error:
            request_id = response.headers.get("x-vercel-id") or response.headers.get("x-request-id")
            detail = response.text[:1000]
            raise RuntimeError(
                f"Vercel Blob upload failed ({response.status_code}); "
                f"request_id={request_id or 'unavailable'}; response={detail}"
            )
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
                quality = result.get("data_quality") or {}
                provider = str(quality.get("provider") or "")
                # Do not surface legacy Yahoo/GC futures or unknown-provider records
                # as current production history. Preserve only the approved Twelve Data
                # feed and explicit DATA UNAVAILABLE records; raw Blob snapshots remain intact.
                approved_provider = provider.startswith("TwelveDataProvider") or provider.startswith("DATA UNAVAILABLE")
                if not approved_provider:
                    continue
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
        logger.exception("Vercel Blob health check failed")
        return {"available": False, "provider": "Vercel Blob (private)", "reason": f"{type(exc).__name__}: {exc}"}
