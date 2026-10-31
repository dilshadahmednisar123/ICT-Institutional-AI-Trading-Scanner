"""
Premium / Discount / Equilibrium Engine
Uses the most recent meaningful confirmed swing high and low as the dealing range.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List, Literal
from .structure import SwingPoint


@dataclass
class DealingRange:
    high: float
    low: float
    equilibrium: float
    levels: dict  # 0, 0.25, 0.5, 0.62, 0.705, 0.79, 1.0
    high_time: Optional[object] = None
    low_time: Optional[object] = None

    def classify(self, price: float, tolerance_pct: float = 0.001) -> Literal["premium", "discount", "equilibrium"]:
        eq = self.equilibrium
        band = abs(self.high - self.low) * tolerance_pct
        if abs(price - eq) <= band:
            return "equilibrium"
        if price > eq:
            return "premium"
        return "discount"

    def fib(self, ratio: float) -> float:
        return self.low + (self.high - self.low) * ratio


def build_dealing_range(
    swings: List[SwingPoint],
    prefer_strength: str = "intermediate",
) -> Optional[DealingRange]:
    """
    Construct dealing range from the latest significant swing high and swing low.
    Prefers intermediate/long term swings when available.
    """
    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]

    if not highs or not lows:
        return None

    # Prefer stronger swings
    def strength_rank(s: SwingPoint) -> int:
        return {"long": 3, "intermediate": 2, "short": 1}.get(s.strength, 1)

    highs = sorted(highs, key=lambda s: (strength_rank(s), s.index), reverse=True)
    lows = sorted(lows, key=lambda s: (strength_rank(s), s.index), reverse=True)

    # Take the most recent meaningful pair that still forms a sensible range
    sh = highs[0]
    sl = lows[0]

    # Ensure high is actually above low; if not, try next candidates
    if sh.price <= sl.price:
        for h in highs:
            for l in lows:
                if h.price > l.price:
                    sh, sl = h, l
                    break
            else:
                continue
            break
        else:
            return None

    high = sh.price
    low = sl.price
    eq = (high + low) / 2.0

    levels = {
        0.0: low,
        0.25: low + (high - low) * 0.25,
        0.5: eq,
        0.62: low + (high - low) * 0.62,
        0.705: low + (high - low) * 0.705,
        0.79: low + (high - low) * 0.79,
        1.0: high,
    }

    return DealingRange(
        high=high,
        low=low,
        equilibrium=eq,
        levels=levels,
        high_time=sh.time,
        low_time=sl.time,
    )
