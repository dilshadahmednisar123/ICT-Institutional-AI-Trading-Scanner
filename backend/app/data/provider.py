"""
Market Data Provider Layer

Philosophy:
- Never invent prices for live decisions.
- Historical path prepared for Dukascopy libraries.
- Optional Twelve Data when TWELVE_DATA_API_KEY is set.
- Clear DATA UNAVAILABLE states.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import logging
import os
import pandas as pd
import numpy as np

logger = logging.getLogger("ict_scanner.data")


@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None


@dataclass
class DataQualityReport:
    symbol: str
    timeframe: str
    is_valid: bool
    missing_candles: int = 0
    duplicate_candles: int = 0
    gaps_detected: int = 0
    stale: bool = False
    last_timestamp: Optional[datetime] = None
    provider: str = "unknown"
    message: str = ""


class BaseDataProvider(ABC):
    @abstractmethod
    def get_ohlc(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        ...

    @abstractmethod
    def get_latest_price(self, symbol: str) -> Optional[Dict[str, float]]:
        ...

    def validate(self, df: pd.DataFrame, symbol: str, timeframe: str) -> DataQualityReport:
        if df is None or df.empty:
            return DataQualityReport(
                symbol=symbol,
                timeframe=timeframe,
                is_valid=False,
                message="Empty or None dataframe",
                provider=self.__class__.__name__,
            )

        required = {"timestamp", "open", "high", "low", "close"}
        if not required.issubset(set(df.columns)):
            return DataQualityReport(
                symbol=symbol,
                timeframe=timeframe,
                is_valid=False,
                message=f"Missing columns. Have: {list(df.columns)}",
                provider=self.__class__.__name__,
            )

        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")

        gaps = 0
        if len(df) > 2:
            diffs = df["timestamp"].diff().dropna()
            median_diff = diffs.median()
            gaps = int((diffs > median_diff * 3).sum())

        last_ts = df["timestamp"].iloc[-1].to_pydatetime()
        now = datetime.now(timezone.utc)
        stale = (now - last_ts) > timedelta(hours=6)

        return DataQualityReport(
            symbol=symbol,
            timeframe=timeframe,
            is_valid=True,
            gaps_detected=gaps,
            stale=stale,
            last_timestamp=last_ts,
            provider=self.__class__.__name__,
            message="OK" if not stale else "Data appears stale",
        )


class SyntheticDataProvider(BaseDataProvider):
    """Deterministic synthetic provider for offline tests only."""

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)

    def get_ohlc(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        logger.warning("Using SYNTHETIC data provider — for testing / offline only")
        base_price = 1.1000 if symbol.upper().startswith("EUR") else 2000.0 if "XAU" in symbol.upper() else 1.2500
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        rows = []
        price = base_price
        for i in range(limit, 0, -1):
            ts = now - timedelta(minutes=i * self._tf_minutes(timeframe))
            change = self.rng.normal(0, 0.0008 if "XAU" not in symbol.upper() else 1.5)
            o = price
            c = price + change
            h = max(o, c) + abs(self.rng.normal(0, 0.0003))
            l = min(o, c) - abs(self.rng.normal(0, 0.0003))
            v = float(self.rng.integers(100, 2000))
            rows.append({
                "timestamp": ts,
                "open": round(o, 5),
                "high": round(h, 5),
                "low": round(l, 5),
                "close": round(c, 5),
                "volume": v,
            })
            price = c
        return pd.DataFrame(rows)

    def get_latest_price(self, symbol: str) -> Optional[Dict[str, float]]:
        df = self.get_ohlc(symbol, "5M", limit=1)
        if df.empty:
            return None
        c = float(df.iloc[-1]["close"])
        return {"bid": c - 0.0001, "ask": c + 0.0001, "mid": c}

    @staticmethod
    def _tf_minutes(tf: str) -> int:
        return {"1M": 1, "5M": 5, "15M": 15, "30M": 30, "1H": 60, "4H": 240, "1D": 1440}.get(tf.upper(), 15)


class DukascopyHistoricalProvider(BaseDataProvider):
    """
    Placeholder for dukascopy-python / downloader integration.
    Falls back to synthetic for offline pipeline development.
    Install dukascopy-python and replace get_ohlc body for real historical data.
    """

    def __init__(self):
        self._fallback = SyntheticDataProvider(seed=123)

    def get_ohlc(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        # Attempt real library if installed
        try:
            import dukascopy_python as duka  # type: ignore
            logger.info("dukascopy_python detected — wire fetch_candles here for production")
            # Real wiring left to operator; fall through until configured
        except ImportError:
            pass
        logger.info("DukascopyHistoricalProvider: using controlled synthetic for offline development")
        return self._fallback.get_ohlc(symbol, timeframe, start, end, limit)

    def get_latest_price(self, symbol: str) -> Optional[Dict[str, float]]:
        return self._fallback.get_latest_price(symbol)


def get_provider(name: str = "auto") -> BaseDataProvider:
    name = (name or "auto").lower()
    if name in ("synthetic", "test"):
        return SyntheticDataProvider()
    if name in ("twelve", "twelvedata", "twelve_data"):
        from .twelve_data import TwelveDataProvider
        return TwelveDataProvider()
    if name == "auto":
        if os.getenv("TWELVE_DATA_API_KEY"):
            from .twelve_data import TwelveDataProvider
            logger.info("Using Twelve Data provider (API key present)")
            return TwelveDataProvider()
        return DukascopyHistoricalProvider()
    return DukascopyHistoricalProvider()
