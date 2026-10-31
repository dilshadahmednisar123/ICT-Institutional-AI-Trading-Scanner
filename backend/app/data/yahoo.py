"""Public Yahoo Finance chart adapter for FX/metals; never fabricates candles."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Dict
import logging
import httpx
import pandas as pd

from .provider import BaseDataProvider

logger = logging.getLogger("ict_scanner.data.yahoo")

class YahooFinanceProvider(BaseDataProvider):
    """Fetches real Yahoo Finance chart data. Empty response means DATA UNAVAILABLE."""

    SYMBOLS = {
        "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X",
        "USDCHF": "CHF=X", "USDCAD": "CAD=X", "AUDUSD": "AUDUSD=X",
        "NZDUSD": "NZDUSD=X", "XAUUSD": "GC=F", "XAGUSD": "XAGUSD=X",
        "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X", "EURGBP": "EURGBP=X",
        "AUDJPY": "AUDJPY=X", "CADJPY": "CADJPY=X", "CHFJPY": "CHFJPY=X",
        "NZDJPY": "NZDJPY=X", "GBPCHF": "GBPCHF=X", "EURCHF": "EURCHF=X",
        "EURAUD": "EURAUD=X", "EURCAD": "EURCAD=X", "EURNZD": "EURNZD=X",
        "GBPAUD": "GBPAUD=X", "GBPCAD": "GBPCAD=X", "GBPNZD": "GBPNZD=X",
        "AUDNZD": "AUDNZD=X", "AUDCAD": "AUDCAD=X", "AUDCHF": "AUDCHF=X",
        "NZDCAD": "NZDCAD=X", "NZDCHF": "NZDCHF=X", "CADCHF": "CADCHF=X",
    }

    INTERVALS = {
        "1M": ("1m", "1d"), "5M": ("5m", "5d"), "15M": ("15m", "60d"),
        "30M": ("30m", "60d"), "1H": ("60m", "730d"),
        "4H": ("60m", "730d"), "1D": ("1d", "max"),
    }

    def get_ohlc(self, symbol: str, timeframe: str,
                 start: Optional[datetime] = None, end: Optional[datetime] = None,
                 limit: int = 500) -> pd.DataFrame:
        symbol = symbol.upper()
        ticker = self.SYMBOLS.get(symbol)
        interval, period = self.INTERVALS.get(timeframe.upper(), ("15m", "60d"))
        if not ticker:
            logger.warning("Yahoo Finance mapping unavailable for %s", symbol)
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {"range": period, "interval": interval, "includePrePost": "true", "events": "div,splits"}
        if start and end:
            params.pop("range", None)
            params["period1"] = str(int(start.replace(tzinfo=timezone.utc).timestamp()))
            params["period2"] = str(int(end.replace(tzinfo=timezone.utc).timestamp()))
        try:
            response = httpx.get(url, params=params, timeout=15.0, headers={
                "User-Agent": "Mozilla/5.0 (compatible; LiquidityNexus/1.0)"
            })
            response.raise_for_status()
            payload = response.json()
            result = payload.get("chart", {}).get("result")
            if not result:
                logger.warning("Yahoo Finance returned no chart for %s: %s", symbol,
                               payload.get("chart", {}).get("error"))
                return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
            item = result[0]
            timestamps = item.get("timestamp") or []
            quote = (item.get("indicators", {}).get("quote") or [{}])[0]
            if not timestamps:
                return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
            df = pd.DataFrame({
                "timestamp": pd.to_datetime(timestamps, unit="s", utc=True),
                "open": quote.get("open", []), "high": quote.get("high", []),
                "low": quote.get("low", []), "close": quote.get("close", []),
                "volume": quote.get("volume", [0] * len(timestamps)),
            }).dropna(subset=["open", "high", "low", "close"])
            if timeframe.upper() == "4H" and not df.empty:
                df = (df.set_index("timestamp")
                      .resample("4h").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
                      .dropna().reset_index())
            if timeframe.upper() == "1D" and not df.empty:
                df = (df.set_index("timestamp")
                      .resample("1D").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
                      .dropna().reset_index())
            return df.tail(limit).reset_index(drop=True)
        except Exception as exc:
            logger.warning("Yahoo Finance fetch failed for %s (%s): %s", symbol, ticker, exc)
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    def get_latest_price(self, symbol: str) -> Optional[Dict[str, float]]:
        df = self.get_ohlc(symbol, "5M", limit=2)
        if df.empty:
            return None
        mid = float(df.iloc[-1]["close"])
        return {"mid": mid}
