"""
Twelve Data live/historical adapter (optional)

Requires TWELVE_DATA_API_KEY in environment.
Free tier is rate-limited — respect limits; never invent candles on failure.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import os
import logging
import pandas as pd
import httpx

from .provider import BaseDataProvider

logger = logging.getLogger("ict_scanner.twelve")

TF_MAP = {
    "1M": "1min",
    "5M": "5min",
    "15M": "15min",
    "30M": "30min",
    "1H": "1h",
    "4H": "4h",
    "1D": "1day",
    "1W": "1week",
}


class TwelveDataProvider(BaseDataProvider):
    BASE = "https://api.twelvedata.com"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TWELVE_DATA_API_KEY", "")

    def get_ohlc(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        if not self.api_key:
            logger.warning("TWELVE_DATA_API_KEY missing — DATA UNAVAILABLE path via empty frame")
            return pd.DataFrame()

        interval = TF_MAP.get(timeframe.upper(), "15min")
        # Twelve Data uses symbols like EUR/USD
        pair = symbol.upper()
        if len(pair) == 6 and "/" not in pair:
            pair = f"{pair[:3]}/{pair[3:]}"

        params = {
            "symbol": pair,
            "interval": interval,
            "outputsize": min(limit, 5000),
            "apikey": self.api_key,
            "format": "JSON",
            "timezone": "UTC",
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                r = client.get(f"{self.BASE}/time_series", params=params)
                r.raise_for_status()
                data = r.json()
            if "values" not in data:
                logger.error("Twelve Data error: %s", data.get("message") or data)
                return pd.DataFrame()
            rows = []
            for v in reversed(data["values"]):
                rows.append({
                    "timestamp": pd.Timestamp(v["datetime"], tz="UTC"),
                    "open": float(v["open"]),
                    "high": float(v["high"]),
                    "low": float(v["low"]),
                    "close": float(v["close"]),
                    "volume": float(v.get("volume") or 0),
                })
            frame = pd.DataFrame(rows)
            frame.attrs["provider"] = (
                "TwelveDataProvider (XAU/USD spot reference; not broker-specific)"
                if symbol.upper() == "XAUUSD"
                else "TwelveDataProvider"
            )
            return frame
        except Exception as exc:
            logger.exception("Twelve Data fetch failed: %s", exc)
            return pd.DataFrame()

    def get_latest_price(self, symbol: str) -> Optional[Dict[str, float]]:
        if not self.api_key:
            return None
        pair = symbol.upper()
        if len(pair) == 6 and "/" not in pair:
            pair = f"{pair[:3]}/{pair[3:]}"
        try:
            with httpx.Client(timeout=15.0) as client:
                r = client.get(
                    f"{self.BASE}/price",
                    params={"symbol": pair, "apikey": self.api_key},
                )
                r.raise_for_status()
                data = r.json()
            price = float(data.get("price", 0))
            if price <= 0:
                return None
            return {"mid": price, "bid": price, "ask": price}
        except Exception:
            logger.exception("Twelve Data price failed")
            return None
