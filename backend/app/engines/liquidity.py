"""
Complete Liquidity Engine — BSL / SSL, Equal Highs/Lows, Sweep Detection
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Literal, Tuple
import pandas as pd
import numpy as np

from .structure import SwingPoint, find_swing_points


@dataclass
class LiquidityPool:
    price: float
    side: Literal["BSL", "SSL"]  # Buy-Side Liquidity / Sell-Side Liquidity
    kind: str  # swing_high, equal_highs, pdh, pwh, session_high, etc.
    strength: float  # 0-100 heuristic
    touches: int = 1
    timeframe: str = "15M"
    formation_time: Optional[datetime] = None
    swept: bool = False
    swept_time: Optional[datetime] = None
    remaining: bool = True


@dataclass
class LiquiditySweep:
    side: Literal["bullish", "bearish"]  # bullish = SSL swept then reclaim
    pool: LiquidityPool
    sweep_price: float
    reclaim_confirmed: bool
    displacement_follow: bool = False
    mss_follow: bool = False
    classification: Literal[
        "potential", "confirmed", "with_displacement", "with_mss", "failed", "continuation"
    ] = "potential"
    time: Optional[datetime] = None


def detect_equal_levels(
    swings: List[SwingPoint],
    tolerance_pct: float = 0.00015,  # ~1.5 pips on EURUSD scale; adjust per instrument
    min_touches: int = 2,
) -> List[LiquidityPool]:
    """Cluster swing highs/lows that are within tolerance → equal highs / equal lows."""
    pools: List[LiquidityPool] = []

    highs = sorted([s for s in swings if s.kind == "high"], key=lambda x: x.price)
    lows = sorted([s for s in swings if s.kind == "low"], key=lambda x: x.price)

    def cluster(points: List[SwingPoint], side: str) -> List[LiquidityPool]:
        if not points:
            return []
        clusters = []
        current = [points[0]]
        for p in points[1:]:
            ref = np.mean([c.price for c in current])
            if abs(p.price - ref) / ref <= tolerance_pct:
                current.append(p)
            else:
                if len(current) >= min_touches:
                    avg = float(np.mean([c.price for c in current]))
                    clusters.append(
                        LiquidityPool(
                            price=avg,
                            side="BSL" if side == "high" else "SSL",
                            kind="equal_highs" if side == "high" else "equal_lows",
                            strength=min(100.0, 40 + len(current) * 15),
                            touches=len(current),
                            formation_time=current[-1].time,
                        )
                    )
                current = [p]
        if len(current) >= min_touches:
            avg = float(np.mean([c.price for c in current]))
            clusters.append(
                LiquidityPool(
                    price=avg,
                    side="BSL" if side == "high" else "SSL",
                    kind="equal_highs" if side == "high" else "equal_lows",
                    strength=min(100.0, 40 + len(current) * 15),
                    touches=len(current),
                    formation_time=current[-1].time,
                )
            )
        return clusters

    pools.extend(cluster(highs, "high"))
    pools.extend(cluster(lows, "low"))
    return pools


def build_liquidity_map(
    df: pd.DataFrame,
    swings: List[SwingPoint],
    timeframe: str = "15M",
    include_session: bool = True,
) -> List[LiquidityPool]:
    """
    Build a ranked list of liquidity pools from swings + equal levels.
    Session highs/lows and previous day/week require additional calendar logic
    (to be expanded).
    """
    pools: List[LiquidityPool] = []

    for s in swings:
        pools.append(
            LiquidityPool(
                price=s.price,
                side="BSL" if s.kind == "high" else "SSL",
                kind=f"swing_{s.kind}",
                strength=30.0 if s.strength == "short" else 55.0 if s.strength == "intermediate" else 80.0,
                touches=1,
                timeframe=timeframe,
                formation_time=s.time,
            )
        )

    equal = detect_equal_levels(swings)
    pools.extend(equal)

    # Simple previous-day high/low approximation using last 24h of data if available
    if len(df) > 20 and "timestamp" in df.columns:
        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        last_ts = df["timestamp"].iloc[-1]
        day_ago = last_ts - pd.Timedelta(hours=24)
        day_slice = df[df["timestamp"] >= day_ago]
        if not day_slice.empty:
            pdh = float(day_slice["high"].max())
            pdl = float(day_slice["low"].min())
            pools.append(
                LiquidityPool(
                    price=pdh,
                    side="BSL",
                    kind="previous_day_high",
                    strength=70.0,
                    timeframe=timeframe,
                    formation_time=last_ts.to_pydatetime(),
                )
            )
            pools.append(
                LiquidityPool(
                    price=pdl,
                    side="SSL",
                    kind="previous_day_low",
                    strength=70.0,
                    timeframe=timeframe,
                    formation_time=last_ts.to_pydatetime(),
                )
            )

    # Deduplicate very close levels
    pools = _dedupe_pools(pools, tolerance_pct=0.0001)
    pools.sort(key=lambda p: p.strength, reverse=True)
    return pools


def _dedupe_pools(pools: List[LiquidityPool], tolerance_pct: float) -> List[LiquidityPool]:
    if not pools:
        return []
    pools = sorted(pools, key=lambda p: p.price)
    cleaned = [pools[0]]
    for p in pools[1:]:
        if abs(p.price - cleaned[-1].price) / cleaned[-1].price > tolerance_pct:
            cleaned.append(p)
        else:
            # keep the stronger one
            if p.strength > cleaned[-1].strength:
                cleaned[-1] = p
    return cleaned


def detect_sweeps(
    df: pd.DataFrame,
    pools: List[LiquidityPool],
    lookback: int = 50,
) -> List[LiquiditySweep]:
    """
    Detect liquidity sweeps (raid then reclaim).

    Bullish sweep: price trades below SSL then reclaims (closes back above).
    Bearish sweep: price trades above BSL then falls back below.
    """
    if df.empty or not pools:
        return []

    df = df.tail(lookback).copy().reset_index(drop=True)
    sweeps: List[LiquiditySweep] = []

    times = pd.to_datetime(df["timestamp"]) if "timestamp" in df.columns else df.index

    for pool in pools:
        if not pool.remaining:
            continue

        for i in range(1, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i - 1]

            if pool.side == "SSL":
                # Price wicked or closed below the pool
                if row["low"] < pool.price and prev["close"] >= pool.price:
                    # Look for reclaim in subsequent candles
                    for j in range(i, min(i + 8, len(df))):
                        if df.iloc[j]["close"] > pool.price:
                            sweeps.append(
                                LiquiditySweep(
                                    side="bullish",
                                    pool=pool,
                                    sweep_price=float(row["low"]),
                                    reclaim_confirmed=True,
                                    classification="confirmed",
                                    time=times[j].to_pydatetime() if hasattr(times[j], "to_pydatetime") else times[j],
                                )
                            )
                            pool.swept = True
                            pool.swept_time = times[j]
                            break
                    break

            elif pool.side == "BSL":
                if row["high"] > pool.price and prev["close"] <= pool.price:
                    for j in range(i, min(i + 8, len(df))):
                        if df.iloc[j]["close"] < pool.price:
                            sweeps.append(
                                LiquiditySweep(
                                    side="bearish",
                                    pool=pool,
                                    sweep_price=float(row["high"]),
                                    reclaim_confirmed=True,
                                    classification="confirmed",
                                    time=times[j].to_pydatetime() if hasattr(times[j], "to_pydatetime") else times[j],
                                )
                            )
                            pool.swept = True
                            pool.swept_time = times[j]
                            break
                    break

    return sweeps


def rank_targets(
    pools: List[LiquidityPool],
    current_price: float,
    direction: Literal["BUY", "SELL"],
    max_targets: int = 5,
) -> List[LiquidityPool]:
    """
    Rank opposing liquidity for take-profit selection.
    BUY → look for BSL above price
    SELL → look for SSL below price
    """
    if direction == "BUY":
        candidates = [p for p in pools if p.side == "BSL" and p.price > current_price and p.remaining]
    else:
        candidates = [p for p in pools if p.side == "SSL" and p.price < current_price and p.remaining]

    # Prefer higher strength, then closer distance (but not tiny noise)
    def score(p: LiquidityPool) -> tuple[float, float]:
        dist = abs(p.price - current_price) / current_price
        # Penalize tiny internal levels, then prefer the nearer pool at equal strength.
        dist_penalty = 10.0 if dist <= 0.001 else 0.0
        return (p.strength - dist_penalty * 5, -abs(p.price - current_price))

    candidates.sort(key=score, reverse=True)
    return candidates[:max_targets]
