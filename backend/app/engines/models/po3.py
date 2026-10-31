"""
ICT Power of Three (PO3) / AMD Model

Phases:
1. Accumulation — range / consolidation near session or daily open
2. Manipulation — false break / liquidity raid of the range
3. Distribution — true directional expansion toward opposing liquidity

This implementation detects the three phases from OHLC structure.
It does not claim certainty about institutional intent from candles alone.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Literal, Dict, Any
from enum import Enum
import pandas as pd

from ..liquidity import LiquiditySweep, LiquidityPool
from ..displacement import DisplacementEvent
from ..entry_risk import build_trade_levels, TradeLevels


class PO3State(str, Enum):
    IDLE = "IDLE"
    ACCUMULATION = "ACCUMULATION"
    MANIPULATION = "MANIPULATION"
    DISTRIBUTION = "DISTRIBUTION"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"


@dataclass
class PO3Setup:
    symbol: str
    direction: Literal["BUY", "SELL"]
    state: PO3State = PO3State.IDLE
    htf_bias: str = "neutral"
    range_high: Optional[float] = None
    range_low: Optional[float] = None
    sweep: Optional[LiquiditySweep] = None
    displacement: Optional[DisplacementEvent] = None
    levels: Optional[TradeLevels] = None
    score: float = 0.0
    notes: List[str] = field(default_factory=list)
    formed_at: Optional[str] = None
    last_updated: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": "ICT_PO3_AMD",
            "symbol": self.symbol,
            "direction": self.direction,
            "state": self.state.value,
            "htf_bias": self.htf_bias,
            "setup_status": "CONFIRMED"
            if self.state == PO3State.CONFIRMED
            else "DEVELOPING"
            if self.state not in (PO3State.IDLE, PO3State.INVALIDATED)
            else "NO_SETUP",
            "score": self.score,
            "notes": self.notes,
            "accumulation_range": {"high": self.range_high, "low": self.range_low},
            "sweep": {
                "side": self.sweep.side,
                "sweep_price": self.sweep.sweep_price,
                "pool_price": self.sweep.pool.price,
            }
            if self.sweep
            else None,
            "displacement_quality": self.displacement.quality_score if self.displacement else None,
            "levels": {
                "entry": self.levels.entry_price,
                "entry_type": self.levels.entry_type,
                "stop_loss": self.levels.stop_loss,
                "stop_reason": self.levels.stop_reason,
                "tp1": self.levels.take_profit_1,
                "tp2": self.levels.take_profit_2,
                "primary_tp": self.levels.primary_tp,
                "risk_reward": self.levels.risk_reward,
                "valid": self.levels.valid,
                "rejection_reason": self.levels.rejection_reason,
            }
            if self.levels
            else None,
            "formed_at": self.formed_at,
            "last_updated": self.last_updated,
        }


def _detect_recent_range(df: pd.DataFrame, lookback: int = 20) -> Optional[tuple[float, float]]:
    if len(df) < lookback:
        return None
    window = df.tail(lookback)
    hi = float(window["high"].max())
    lo = float(window["low"].min())
    if hi <= lo:
        return None
    # Require a relatively tight range vs recent ATR-ish expansion later
    return hi, lo


def evaluate_po3(
    symbol: str,
    current_price: float,
    htf_bias: str,
    df: pd.DataFrame,
    sweeps: List[LiquiditySweep],
    displacements: List[DisplacementEvent],
    liquidity_pools: List[LiquidityPool],
    atr: Optional[float] = None,
    min_rr: float = 0.0,
) -> List[PO3Setup]:
    results: List[PO3Setup] = []
    ts = datetime.now(timezone.utc).isoformat()

    rng = _detect_recent_range(df, lookback=24)
    if not rng:
        return results

    range_high, range_low = rng
    range_width = range_high - range_low

    for direction, sweep_side, disp_dir in [
        ("BUY", "bullish", "bullish"),   # manipulate lows then distribute up
        ("SELL", "bearish", "bearish"),
    ]:
        setup = PO3Setup(
            symbol=symbol,
            direction=direction,
            htf_bias=htf_bias,
            range_high=range_high,
            range_low=range_low,
            last_updated=ts,
        )
        setup.state = PO3State.ACCUMULATION
        setup.notes.append(f"Accumulation range {range_low:.5f} – {range_high:.5f}")

        # Manipulation = sweep of range extreme
        rel_sweeps = [
            s for s in sweeps
            if s.side == sweep_side
            and s.reclaim_confirmed
            and (
                (direction == "BUY" and s.sweep_price <= range_low + range_width * 0.15)
                or (direction == "SELL" and s.sweep_price >= range_high - range_width * 0.15)
            )
        ]
        if not rel_sweeps:
            # also accept any strong sweep near the range
            rel_sweeps = [
                s for s in sweeps
                if s.side == sweep_side and s.reclaim_confirmed and s.pool.strength >= 50
            ]
        if not rel_sweeps:
            setup.notes.append("No manipulation (liquidity raid) of the range yet")
            results.append(setup)
            continue

        setup.sweep = rel_sweeps[-1]
        setup.state = PO3State.MANIPULATION
        setup.notes.append(
            f"Manipulation sweep @ {setup.sweep.sweep_price:.5f} (pool {setup.sweep.pool.price:.5f})"
        )

        rel_disp = [
            d for d in displacements
            if d.direction == disp_dir and d.quality_score >= 55
        ]
        if not rel_disp:
            setup.notes.append("Manipulation seen — waiting for distribution displacement")
            results.append(setup)
            continue

        setup.displacement = rel_disp[-1]
        setup.state = PO3State.DISTRIBUTION
        setup.notes.append(f"Distribution displacement score {setup.displacement.quality_score}")

        # Entry near mid/reclaim of range after manipulation
        entry = (range_high + range_low) / 2.0
        invalidation = setup.sweep.sweep_price

        levels = build_trade_levels(
            direction=direction,
            symbol=symbol,
            current_price=current_price,
            entry_price=entry,
            entry_type="PO3_DISTRIBUTION",
            invalidation_price=invalidation,
            liquidity_pools=liquidity_pools,
            atr=atr,
            min_rr=min_rr,
            entry_zone_low=range_low,
            entry_zone_high=range_high,
        )
        setup.levels = levels

        if not levels.valid:
            setup.notes.append(f"Levels rejected: {levels.rejection_reason}")
            results.append(setup)
            continue

        # Confirm when price expands beyond the opposite side of the range
        if direction == "BUY" and current_price > range_high:
            setup.state = PO3State.CONFIRMED
            setup.formed_at = ts
            setup.notes.append("PO3 distribution expanding higher — CONFIRMED")
        elif direction == "SELL" and current_price < range_low:
            setup.state = PO3State.CONFIRMED
            setup.formed_at = ts
            setup.notes.append("PO3 distribution expanding lower — CONFIRMED")
        else:
            setup.notes.append("Distribution phase active — expansion pending")

        results.append(setup)

    return results
