"""
Market Data Provider Layer.

Production rule: a provider failure is DATA UNAVAILABLE, never synthetic candles.
Yahoo Finance is a public-data fallback; XAUUSD maps to GC=F futures and is
explicitly labelled as a futures proxy, not spot gold.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import logging
import os

import pandas as pd
import numpy as np

logger = logging.getLogger("ict_scanner.data")
OHLC_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
TF_MINUTES = {"1M": 1, "5M": 5, "15M": 15, "30M": 30, "1H": 60, "4H": 240, "1D": 1440}
# Age is measured from the expected close of the latest candle, not its open.
FRESHNESS_MINUTES = {"1M": 3, "5M": 12, "15M": 35, "30M": 70, "1H": 150, "4H": 600, "1D": 2160}


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
    misaligned_candles: int = 0
    gaps_detected: int = 0
    stale: bool = False
    last_timestamp: Optional[datetime] = None
    provider: str = "unknown"
    message: str = ""
    market_status: str = "unknown"


class BaseDataProvider(ABC):
    @abstractmethod
    def get_ohlc(self, symbol: str, timeframe: str,
                 start: Optional[datetime] = None, end: Optional[datetime] = None,
                 limit: int = 500) -> pd.DataFrame:
        ...

    @abstractmethod
    def get_latest_price(self, symbol: str) -> Optional[Dict[str, float]]:
        ...

    def validate(self, df: pd.DataFrame, symbol: str, timeframe: str) -> DataQualityReport:
        provider_name = self.__class__.__name__
        if df is None or df.empty:
            return DataQualityReport(symbol, timeframe, False, provider=provider_name,
                                     message="No market candles returned", market_status="unavailable")
        required = {"timestamp", "open", "high", "low", "close"}
        if not required.issubset(df.columns):
            return DataQualityReport(symbol, timeframe, False, provider=provider_name,
                                     message=f"Missing OHLC columns: {sorted(required-set(df.columns))}",
                                     market_status="invalid")

        work = df.copy()
        work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True, errors="coerce")
        if work["timestamp"].isna().any():
            return DataQualityReport(symbol, timeframe, False, provider=provider_name,
                                     message="Invalid candle timestamps", market_status="invalid")
        for col in ("open", "high", "low", "close"):
            work[col] = pd.to_numeric(work[col], errors="coerce")
        if work[["open", "high", "low", "close"]].isna().any().any():
            return DataQualityReport(symbol, timeframe, False, provider=provider_name,
                                     message="Non-numeric OHLC values", market_status="invalid")
        invalid_ohlc = (
            (work["high"] < work[["open", "close", "low"]].max(axis=1)) |
            (work["low"] > work[["open", "close", "high"]].min(axis=1)) |
            (work[["open", "high", "low", "close"]] <= 0).any(axis=1)
        )
        if invalid_ohlc.any():
            return DataQualityReport(symbol, timeframe, False, provider=provider_name,
                                     message=f"Invalid OHLC candle(s): {int(invalid_ohlc.sum())}",
                                     market_status="invalid")

        tf = timeframe.upper()
        expected = TF_MINUTES.get(tf, 15)
        misaligned_count = 0
        if tf in ("1M", "5M", "15M", "30M", "1H", "4H"):
            epoch_seconds = work["timestamp"].astype("int64") // 1_000_000_000
            misaligned_count = int((epoch_seconds % (expected * 60) != 0).sum())
        if misaligned_count:
            return DataQualityReport(
                symbol, timeframe, False, misaligned_candles=misaligned_count,
                provider=str(df.attrs.get("provider", provider_name)),
                message=f"{misaligned_count} candle timestamp(s) are not aligned to {timeframe}",
                market_status="invalid",
            )
        duplicate_count = int(work["timestamp"].duplicated(keep="last").sum())
        work = work.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
        diffs = work["timestamp"].diff().dropna()
        # Count intraday missing bars, but do not classify normal session/weekend closures
        # as missing candles. Larger breaks remain visible as a feed/session gap in status.
        max_counted_gap = timedelta(hours=6)
        gap_mask = (diffs > pd.Timedelta(minutes=expected * 1.5)) & (diffs <= max_counted_gap)
        gaps = int(gap_mask.sum())
        missing = 0
        for delta in diffs[gap_mask]:
            missing += max(1, int(round(delta.total_seconds() / (expected * 60))) - 1)

        last_ts = work["timestamp"].iloc[-1].to_pydatetime()
        now = datetime.now(timezone.utc)
        expected_close = last_ts + timedelta(minutes=expected)
        age_minutes = max(0.0, (now - expected_close).total_seconds() / 60.0)
        stale = age_minutes > FRESHNESS_MINUTES.get(tf, 150)
        provider = str(df.attrs.get("provider", provider_name))
        message = "OK" if not stale else f"Feed stale: latest candle closed {age_minutes:.0f} minutes ago"
        weekend_closed = (now.weekday() == 5 or
                          (now.weekday() == 6 and now.hour < 22) or
                          (now.weekday() == 4 and now.hour >= 22))
        market_status = "market_closed" if weekend_closed else ("stale" if stale else "open_or_recent")
        if weekend_closed:
            message = f"Market closed for weekend; last candle closed {age_minutes:.0f} minutes ago"
        return DataQualityReport(
            symbol=symbol, timeframe=timeframe, is_valid=True,
            missing_candles=missing, duplicate_candles=duplicate_count,
            misaligned_candles=misaligned_count, gaps_detected=gaps, stale=stale, last_timestamp=last_ts,
            provider=provider, message=message, market_status=market_status,
        )


class SyntheticDataProvider(BaseDataProvider):
    """Deterministic synthetic provider for unit tests and offline development only."""
    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)

    def get_ohlc(self, symbol: str, timeframe: str, start=None, end=None, limit=500) -> pd.DataFrame:
        logger.warning("Synthetic candles requested; never use for production trading decisions")
        base = 1.1 if symbol.upper().startswith("EUR") else 2000.0 if "XAU" in symbol.upper() else 1.25
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        step = TF_MINUTES.get(timeframe.upper(), 15)
        rows, price = [], base
        for i in range(limit, 0, -1):
            ts = now - timedelta(minutes=i * step)
            change = self.rng.normal(0, 0.0008 if "XAU" not in symbol.upper() else 1.5)
            o, c = price, price + change
            rows.append({"timestamp": ts, "open": o, "high": max(o,c)+abs(self.rng.normal(0,.0003)),
                         "low": min(o,c)-abs(self.rng.normal(0,.0003)), "close": c,
                         "volume": float(self.rng.integers(100,2000))})
            price = c
        return pd.DataFrame(rows)

    def get_latest_price(self, symbol: str) -> Optional[Dict[str, float]]:
        df = self.get_ohlc(symbol, "5M", limit=1)
        if df.empty: return None
        price = float(df.iloc[-1]["close"])
        return {"bid": price-.0001, "ask": price+.0001, "mid": price}


class DukascopyHistoricalProvider(BaseDataProvider):
    """Reserved for a future licensed/implemented Dukascopy adapter; never fabricates data."""
    def get_ohlc(self, symbol: str, timeframe: str, start=None, end=None, limit=500) -> pd.DataFrame:
        logger.error("Dukascopy adapter is not implemented; returning DATA UNAVAILABLE")
        return pd.DataFrame(columns=OHLC_COLUMNS)

    def get_latest_price(self, symbol: str) -> Optional[Dict[str, float]]:
        return None


class AutoDataProvider(BaseDataProvider):
    """Prefer configured Twelve Data; fall back to Yahoo only when it yields better data."""
    def __init__(self):
        from .yahoo import YahooFinanceProvider
        self.yahoo = YahooFinanceProvider()
        self.twelve = None
        if os.getenv("TWELVE_DATA_API_KEY", "").strip():
            try:
                from .twelve_data import TwelveDataProvider
                self.twelve = TwelveDataProvider()
            except Exception as exc:
                logger.warning("Twelve Data adapter unavailable: %s", exc)

    def get_ohlc(self, symbol: str, timeframe: str, start=None, end=None, limit=500) -> pd.DataFrame:
        candidates = []
        if self.twelve is not None:
            try:
                frame = self.twelve.get_ohlc(symbol, timeframe, start, end, limit)
                if frame is not None and not frame.empty:
                    report = self.twelve.validate(frame, symbol, timeframe)
                    candidates.append((0 if not report.stale else 1, 0, -report.last_timestamp.timestamp(), frame))
            except Exception as exc:
                logger.warning("Twelve Data failed for %s; trying Yahoo fallback: %s", symbol, exc)
        try:
            frame = self.yahoo.get_ohlc(symbol, timeframe, start, end, limit)
            if frame is not None and not frame.empty:
                report = self.yahoo.validate(frame, symbol, timeframe)
                candidates.append((0 if not report.stale else 1, 1, -report.last_timestamp.timestamp(), frame))
        except Exception as exc:
            logger.warning("Yahoo Finance failed for %s: %s", symbol, exc)
        if not candidates:
            return pd.DataFrame(columns=OHLC_COLUMNS)
        # Fresh beats stale; among equal freshness choose the newest candle.
        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        return candidates[0][3].tail(limit).reset_index(drop=True)

    def get_latest_price(self, symbol: str) -> Optional[Dict[str, float]]:
        frame = self.get_ohlc(symbol, "5M", limit=2)
        if frame.empty:
            return None
        mid = float(frame.iloc[-1]["close"])
        return {"mid": mid}


def get_provider(name: str = "auto") -> BaseDataProvider:
    name = (name or "auto").lower()
    if name in ("synthetic", "test"):
        return SyntheticDataProvider()
    if name in ("twelve", "twelvedata", "twelve_data"):
        from .twelve_data import TwelveDataProvider
        return TwelveDataProvider()
    if name == "yahoo":
        from .yahoo import YahooFinanceProvider
        return YahooFinanceProvider()
    if name == "auto":
        provider = AutoDataProvider()
        logger.info("Using resilient auto provider (Twelve Data when configured, Yahoo Finance fallback; synthetic disabled)")
        return provider
    if name == "dukascopy":
        return DukascopyHistoricalProvider()
    return AutoDataProvider()
