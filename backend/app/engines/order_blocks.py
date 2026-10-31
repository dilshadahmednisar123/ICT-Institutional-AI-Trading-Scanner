"""
Order Block / Breaker / Mitigation Block Engine — ICT

Rules (simplified but strict):
- Bullish OB: last relevant bearish candle (or cluster) before a confirmed bullish displacement that breaks structure.
- Bearish OB: last relevant bullish candle before a confirmed bearish displacement that breaks structure.
- Breaker: an OB that is invalidated and later acts as opposing reaction zone.
- Mitigation: return to a previously formed institutional zone after displacement.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Literal
import pandas as pd
import numpy as np

from .displacement import DisplacementEvent, detect_displacement
from .structure import SwingPoint, find_swing_points


@dataclass
class OrderBlock:
    direction: Literal["bullish", "bearish"]
    open: float
    high: float
    low: float
    close: float
    midpoint: float
    body_high: float
    body_low: float
    formation_time: datetime
    timeframe: str
    index: int
    invalidated: bool = False
    invalidation_price: Optional[float] = None
    mitigated: bool = False
    mitigation_pct: float = 0.0
    is_breaker: bool = False
    quality: float = 50.0  # 0-100
    origin_displacement_score: float = 0.0

    @property
    def proximal(self) -> float:
        """Nearest edge to current price action (entry-relevant)."""
        return self.body_high if self.direction == "bullish" else self.body_low

    @property
    def distal(self) -> float:
        return self.body_low if self.direction == "bullish" else self.body_high


def _candle_body(row) -> tuple[float, float]:
    o, c = float(row["open"]), float(row["close"])
    return max(o, c), min(o, c)


def detect_order_blocks(
    df: pd.DataFrame,
    displacements: Optional[List[DisplacementEvent]] = None,
    timeframe: str = "15M",
    lookback: int = 200,
    min_disp_score: float = 55.0,
) -> List[OrderBlock]:
    """
    Detect order blocks linked to quality displacement events.
    """
    if len(df) < 20:
        return []

    df = df.tail(lookback).copy().reset_index(drop=True)
    if displacements is None:
        displacements = detect_displacement(df, lookback=lookback)

    times = pd.to_datetime(df["timestamp"]) if "timestamp" in df.columns else df.index
    obs: List[OrderBlock] = []

    for disp in displacements:
        if disp.quality_score < min_disp_score:
            continue

        # Look backward for the last opposite-colored candle before the displacement
        search_start = max(0, disp.index - 12)
        candidate_idx = None

        if disp.direction == "bullish":
            # Last bearish candle before bullish displacement
            for i in range(disp.index - 1, search_start - 1, -1):
                row = df.iloc[i]
                if float(row["close"]) < float(row["open"]):
                    candidate_idx = i
                    break
        else:
            # Last bullish candle before bearish displacement
            for i in range(disp.index - 1, search_start - 1, -1):
                row = df.iloc[i]
                if float(row["close"]) > float(row["open"]):
                    candidate_idx = i
                    break

        if candidate_idx is None:
            continue

        row = df.iloc[candidate_idx]
        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        c = float(row["close"])
        body_high, body_low = _candle_body(row)

        direction: Literal["bullish", "bearish"] = (
            "bullish" if disp.direction == "bullish" else "bearish"
        )

        # Quality boost if the OB is relatively tight and displacement was strong
        width = h - l
        body = abs(c - o)
        tightness = 1.0 - min(1.0, width / (abs(disp.close - disp.open) + 1e-9))
        quality = min(100.0, 40 + disp.quality_score * 0.4 + tightness * 20)

        obs.append(
            OrderBlock(
                direction=direction,
                open=o,
                high=h,
                low=l,
                close=c,
                midpoint=(h + l) / 2.0,
                body_high=body_high,
                body_low=body_low,
                formation_time=times[candidate_idx].to_pydatetime()
                if hasattr(times[candidate_idx], "to_pydatetime")
                else times[candidate_idx],
                timeframe=timeframe,
                index=candidate_idx,
                quality=round(quality, 1),
                origin_displacement_score=disp.quality_score,
                invalidation_price=l if direction == "bullish" else h,
            )
        )

    # Update mitigation / invalidation against later price action
    for ob in obs:
        for i in range(ob.index + 1, len(df)):
            row = df.iloc[i]
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])

            if ob.direction == "bullish":
                # Mitigation when price trades into the OB from above
                if low <= ob.high:
                    penetrated = max(0.0, min(1.0, (ob.high - low) / (ob.high - ob.low + 1e-9)))
                    ob.mitigation_pct = max(ob.mitigation_pct, penetrated)
                    if low <= ob.low:
                        ob.mitigated = True
                # Invalidation: close below distal
                if close < ob.low:
                    ob.invalidated = True
                    break
            else:
                if high >= ob.low:
                    penetrated = max(0.0, min(1.0, (high - ob.low) / (ob.high - ob.low + 1e-9)))
                    ob.mitigation_pct = max(ob.mitigation_pct, penetrated)
                    if high >= ob.high:
                        ob.mitigated = True
                if close > ob.high:
                    ob.invalidated = True
                    break

    return obs


def detect_breakers(
    order_blocks: List[OrderBlock],
    df: pd.DataFrame,
) -> List[OrderBlock]:
    """
    Mark order blocks that have been invalidated and can act as breakers.
    A full breaker model also requires a subsequent structural reversal + retest.
    Here we flag invalidated OBs of sufficient quality.
    """
    breakers = []
    for ob in order_blocks:
        if ob.invalidated and ob.quality >= 50:
            ob.is_breaker = True
            # Flip perspective for reaction
            breakers.append(ob)
    return breakers


def get_active_order_blocks(
    obs: List[OrderBlock],
    current_price: float,
    direction: Optional[Literal["bullish", "bearish"]] = None,
    max_mitigation: float = 0.7,
) -> List[OrderBlock]:
    active = []
    for ob in obs:
        if ob.invalidated:
            continue
        if ob.mitigation_pct > max_mitigation:
            continue
        if direction and ob.direction != direction:
            continue
        # Prefer blocks that price can still interact with
        if ob.direction == "bullish" and current_price > ob.high * 1.005:
            continue
        if ob.direction == "bearish" and current_price < ob.low * 0.995:
            continue
        active.append(ob)
    active.sort(key=lambda x: x.quality, reverse=True)
    return active
