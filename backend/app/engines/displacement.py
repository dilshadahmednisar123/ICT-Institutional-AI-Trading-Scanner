"""
Displacement Engine — Institutional-style impulsive candles
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Literal
import pandas as pd
import numpy as np


@dataclass
class DisplacementEvent:
    direction: Literal["bullish", "bearish"]
    time: datetime
    open: float
    high: float
    low: float
    close: float
    body: float
    range_: float
    body_to_range: float
    atr_multiple: float
    quality_score: float  # 0-100
    index: int
    broke_structure: bool = False


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()


def detect_displacement(
    df: pd.DataFrame,
    atr_period: int = 14,
    min_body_ratio: float = 0.60,
    min_atr_multiple: float = 1.2,
    lookback: int = 100,
) -> List[DisplacementEvent]:
    """
    Detect strong displacement candles.

    Criteria (configurable):
    - Body / Range >= min_body_ratio
    - Range >= min_atr_multiple * ATR
    - Strong directional close
    """
    if len(df) < atr_period + 5:
        return []

    df = df.tail(lookback).copy().reset_index(drop=True)
    atr = compute_atr(df, atr_period)
    times = pd.to_datetime(df["timestamp"]) if "timestamp" in df.columns else df.index

    events: List[DisplacementEvent] = []

    for i in range(len(df)):
        row = df.iloc[i]
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        body = abs(c - o)
        range_ = h - l
        if range_ <= 0:
            continue

        body_ratio = body / range_
        atr_val = float(atr.iloc[i]) if not np.isnan(atr.iloc[i]) else range_
        atr_mult = range_ / atr_val if atr_val > 0 else 0.0

        if body_ratio < min_body_ratio or atr_mult < min_atr_multiple:
            continue

        direction: Literal["bullish", "bearish"] = "bullish" if c > o else "bearish"

        # Quality score
        score = 0.0
        score += min(40.0, body_ratio * 50)          # body dominance
        score += min(30.0, atr_mult * 12)             # size vs ATR
        # close near extreme
        if direction == "bullish":
            close_pos = (c - l) / range_
        else:
            close_pos = (h - c) / range_
        score += min(20.0, close_pos * 25)
        # small wick opposite side is better
        score = min(100.0, score)

        events.append(
            DisplacementEvent(
                direction=direction,
                time=times[i].to_pydatetime() if hasattr(times[i], "to_pydatetime") else times[i],
                open=o,
                high=h,
                low=l,
                close=c,
                body=body,
                range_=range_,
                body_to_range=body_ratio,
                atr_multiple=atr_mult,
                quality_score=round(score, 1),
                index=i,
            )
        )

    return events
