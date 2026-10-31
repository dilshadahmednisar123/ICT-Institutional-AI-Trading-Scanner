"""
Fair Value Gap (FVG) Detection Engine — ICT
Bullish FVG: Candle1.high < Candle3.low
Bearish FVG: Candle1.low > Candle3.high
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Literal
import pandas as pd


@dataclass
class FairValueGap:
    direction: Literal["bullish", "bearish"]
    upper: float
    lower: float
    midpoint: float  # Consequent Encroachment (CE)
    width: float
    formation_time: datetime
    timeframe: str
    candle_indices: tuple[int, int, int]
    mitigated_pct: float = 0.0
    is_filled: bool = False
    is_invalidated: bool = False
    created_by_displacement: bool = False
    htf_aligned: Optional[bool] = None

    def contains(self, price: float) -> bool:
        return self.lower <= price <= self.upper

    def update_mitigation(self, current_high: float, current_low: float) -> None:
        if self.direction == "bullish":
            # Price trading down into the gap mitigates from top
            if current_low < self.upper:
                mitigated = max(0.0, min(1.0, (self.upper - current_low) / self.width))
                self.mitigated_pct = max(self.mitigated_pct, mitigated)
                if current_low <= self.lower:
                    self.is_filled = True
        else:
            if current_high > self.lower:
                mitigated = max(0.0, min(1.0, (current_high - self.lower) / self.width))
                self.mitigated_pct = max(self.mitigated_pct, mitigated)
                if current_high >= self.upper:
                    self.is_filled = True


def detect_fvgs(
    df: pd.DataFrame,
    timeframe: str = "15M",
    min_width_pips: float = 0.0,
    lookback: int = 500,
) -> List[FairValueGap]:
    """
    Detect standard 3-candle Fair Value Gaps.
    Requires columns: open, high, low, close, timestamp (or index as datetime).
    """
    if len(df) < 3:
        return []

    df = df.tail(lookback).copy()
    if "timestamp" in df.columns:
        times = pd.to_datetime(df["timestamp"])
    else:
        times = df.index

    fvgs: List[FairValueGap] = []

    for i in range(2, len(df)):
        c1 = df.iloc[i - 2]
        c2 = df.iloc[i - 1]  # middle candle (displacement often here)
        c3 = df.iloc[i]

        # Bullish FVG
        if c1["high"] < c3["low"]:
            upper = float(c3["low"])
            lower = float(c1["high"])
            width = upper - lower
            if width >= min_width_pips:
                mid = (upper + lower) / 2.0
                fvgs.append(
                    FairValueGap(
                        direction="bullish",
                        upper=upper,
                        lower=lower,
                        midpoint=mid,
                        width=width,
                        formation_time=times[i],
                        timeframe=timeframe,
                        candle_indices=(i - 2, i - 1, i),
                    )
                )

        # Bearish FVG
        if c1["low"] > c3["high"]:
            upper = float(c1["low"])
            lower = float(c3["high"])
            width = upper - lower
            if width >= min_width_pips:
                mid = (upper + lower) / 2.0
                fvgs.append(
                    FairValueGap(
                        direction="bearish",
                        upper=upper,
                        lower=lower,
                        midpoint=mid,
                        width=width,
                        formation_time=times[i],
                        timeframe=timeframe,
                        candle_indices=(i - 2, i - 1, i),
                    )
                )

    return fvgs


def get_active_fvgs(
    fvgs: List[FairValueGap],
    current_price: float,
    direction: Optional[Literal["bullish", "bearish"]] = None,
    max_mitigation: float = 0.5,
) -> List[FairValueGap]:
    """Return unfilled / partially mitigated FVGs near current price."""
    active = []
    for fvg in fvgs:
        if fvg.is_filled or fvg.is_invalidated:
            continue
        if fvg.mitigated_pct > max_mitigation:
            continue
        if direction and fvg.direction != direction:
            continue
        # Prefer those that price can still interact with
        if fvg.direction == "bullish" and current_price > fvg.upper * 1.002:
            continue
        if fvg.direction == "bearish" and current_price < fvg.lower * 0.998:
            continue
        active.append(fvg)
    return active
