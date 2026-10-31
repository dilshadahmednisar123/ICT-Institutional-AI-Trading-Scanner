"""
Market Structure Engine — Swings, BOS, CHOCH, MSS
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Literal, Tuple
import pandas as pd
import numpy as np


@dataclass
class SwingPoint:
    price: float
    time: datetime
    kind: Literal["high", "low"]
    strength: Literal["short", "intermediate", "long"] = "short"
    index: int = -1
    confirmed: bool = True


@dataclass
class StructureEvent:
    event_type: Literal["BOS", "CHOCH", "MSS"]
    direction: Literal["bullish", "bearish"]
    price: float
    time: datetime
    broken_level: float
    confirmed_by_close: bool
    timeframe: str


def find_swing_points(
    df: pd.DataFrame,
    left: int = 3,
    right: int = 3,
    strength: Literal["short", "intermediate", "long"] = "short",
) -> List[SwingPoint]:
    """
    Classic pivot detection. Confirmed only after `right` candles have closed.
    Does not repaint confirmed pivots.
    """
    if len(df) < left + right + 1:
        return []
    df = df.reset_index(drop=True)

    highs = df["high"].values
    lows = df["low"].values
    times = pd.to_datetime(df["timestamp"]) if "timestamp" in df.columns else df.index

    swings: List[SwingPoint] = []

    for i in range(left, len(df) - right):
        # Swing High
        if highs[i] == max(highs[i - left : i + right + 1]):
            swings.append(
                SwingPoint(
                    price=float(highs[i]),
                    time=times[i],
                    kind="high",
                    strength=strength,
                    index=i,
                    confirmed=True,
                )
            )
        # Swing Low
        if lows[i] == min(lows[i - left : i + right + 1]):
            swings.append(
                SwingPoint(
                    price=float(lows[i]),
                    time=times[i],
                    kind="low",
                    strength=strength,
                    index=i,
                    confirmed=True,
                )
            )

    return swings


def classify_structure(swings: List[SwingPoint]) -> dict:
    """
    Return latest HH/HL/LH/LL sequence and current bias.
    """
    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]

    result = {
        "bias": "neutral",
        "last_hh": None,
        "last_hl": None,
        "last_lh": None,
        "last_ll": None,
        "structure": [],
    }

    if len(highs) < 2 or len(lows) < 2:
        return result

    # Simple sequential classification
    for i in range(1, len(highs)):
        if highs[i].price > highs[i - 1].price:
            result["structure"].append(("HH", highs[i]))
            result["last_hh"] = highs[i]
        else:
            result["structure"].append(("LH", highs[i]))
            result["last_lh"] = highs[i]

    for i in range(1, len(lows)):
        if lows[i].price > lows[i - 1].price:
            result["structure"].append(("HL", lows[i]))
            result["last_hl"] = lows[i]
        else:
            result["structure"].append(("LL", lows[i]))
            result["last_ll"] = lows[i]

    # Bias heuristic
    recent = result["structure"][-4:] if result["structure"] else []
    hh_count = sum(1 for t, _ in recent if t == "HH")
    hl_count = sum(1 for t, _ in recent if t == "HL")
    lh_count = sum(1 for t, _ in recent if t == "LH")
    ll_count = sum(1 for t, _ in recent if t == "LL")

    if hh_count + hl_count > lh_count + ll_count:
        result["bias"] = "bullish"
    elif lh_count + ll_count > hh_count + hl_count:
        result["bias"] = "bearish"

    return result


def detect_bos_choch(
    df: pd.DataFrame,
    swings: List[SwingPoint],
    timeframe: str = "15M",
) -> List[StructureEvent]:
    """Detect one-time close-confirmed breaks of the latest confirmed swing levels."""
    events: List[StructureEvent] = []
    if len(swings) < 2 or len(df) < 5:
        return events
    df = df.reset_index(drop=True)

    times = pd.to_datetime(df["timestamp"]) if "timestamp" in df.columns else df.index
    ordered = sorted(swings, key=lambda swing: swing.index)
    active_bias = classify_structure(ordered).get("bias", "neutral")
    broken_high_indices: set[int] = set()
    broken_low_indices: set[int] = set()

    for i in range(1, len(df)):
        eligible = [s for s in ordered if s.index < i]
        highs = [s for s in eligible if s.kind == "high"]
        lows = [s for s in eligible if s.kind == "low"]
        if not highs or not lows:
            continue
        swing_high, swing_low = highs[-1], lows[-1]
        previous_close = float(df.iloc[i - 1]["close"])
        close = float(df.iloc[i]["close"])
        tv = times[i]
        event_time = tv.to_pydatetime() if hasattr(tv, "to_pydatetime") else tv

        if swing_high.index not in broken_high_indices and previous_close <= swing_high.price < close:
            event_type = "CHOCH" if active_bias == "bearish" else "BOS"
            events.append(StructureEvent(event_type=event_type, direction="bullish", price=close,
                time=event_time, broken_level=swing_high.price, confirmed_by_close=True, timeframe=timeframe))
            broken_high_indices.add(swing_high.index)
            active_bias = "bullish"

        if swing_low.index not in broken_low_indices and previous_close >= swing_low.price > close:
            event_type = "CHOCH" if active_bias == "bullish" else "BOS"
            events.append(StructureEvent(event_type=event_type, direction="bearish", price=close,
                time=event_time, broken_level=swing_low.price, confirmed_by_close=True, timeframe=timeframe))
            broken_low_indices.add(swing_low.index)
            active_bias = "bearish"
    return events
