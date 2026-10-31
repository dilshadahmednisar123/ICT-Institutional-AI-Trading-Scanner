"""
ICT Turtle Soup Model — False Break Reversal

Bullish:
1. Price trades below a meaningful prior low (PDL, swing low, equal lows, etc.)
2. Price reclaims the level
3. Rejection confirmed by closed candle
4. Bullish delivery / displacement confirms reversal
5. Entry on reclaim / minor pullback; SL beyond the sweep extreme
6. Target opposing liquidity

Bearish is the inverse.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Literal, Dict, Any
from enum import Enum

from ..liquidity import LiquiditySweep, LiquidityPool
from ..displacement import DisplacementEvent
from ..entry_risk import build_trade_levels, TradeLevels


class TSState(str, Enum):
    IDLE = "IDLE"
    FALSE_BREAK = "FALSE_BREAK"
    RECLAIM = "RECLAIM"
    DISPLACEMENT = "DISPLACEMENT"
    ENTRY_READY = "ENTRY_READY"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"


@dataclass
class TurtleSoupSetup:
    symbol: str
    direction: Literal["BUY", "SELL"]
    state: TSState = TSState.IDLE
    htf_bias: str = "neutral"
    sweep: Optional[LiquiditySweep] = None
    displacement: Optional[DisplacementEvent] = None
    reference_level: Optional[float] = None
    levels: Optional[TradeLevels] = None
    score: float = 0.0
    notes: List[str] = field(default_factory=list)
    formed_at: Optional[str] = None
    last_updated: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": "ICT_Turtle_Soup",
            "symbol": self.symbol,
            "direction": self.direction,
            "state": self.state.value,
            "htf_bias": self.htf_bias,
            "setup_status": "CONFIRMED"
            if self.state == TSState.CONFIRMED
            else "DEVELOPING"
            if self.state not in (TSState.IDLE, TSState.INVALIDATED)
            else "NO_SETUP",
            "score": self.score,
            "notes": self.notes,
            "reference_level": self.reference_level,
            "sweep": {
                "side": self.sweep.side,
                "sweep_price": self.sweep.sweep_price,
                "pool_price": self.sweep.pool.price,
                "pool_kind": self.sweep.pool.kind,
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


def evaluate_turtle_soup(
    symbol: str,
    current_price: float,
    htf_bias: str,
    sweeps: List[LiquiditySweep],
    displacements: List[DisplacementEvent],
    liquidity_pools: List[LiquidityPool],
    atr: Optional[float] = None,
    min_rr: float = 0.0,
) -> List[TurtleSoupSetup]:
    results: List[TurtleSoupSetup] = []
    ts = datetime.now(timezone.utc).isoformat()

    for direction, sweep_side, disp_dir in [
        ("BUY", "bullish", "bullish"),
        ("SELL", "bearish", "bearish"),
    ]:
        setup = TurtleSoupSetup(
            symbol=symbol,
            direction=direction,
            htf_bias=htf_bias,
            last_updated=ts,
        )

        # Prefer sweeps of meaningful levels (PDH/PDL, equal highs/lows, stronger swings)
        relevant = [
            s
            for s in sweeps
            if s.side == sweep_side
            and s.reclaim_confirmed
            and s.pool.strength >= 40
        ]
        if not relevant:
            setup.notes.append("No confirmed false-break of meaningful level")
            results.append(setup)
            continue

        # Prefer higher-strength pools
        relevant.sort(key=lambda s: s.pool.strength, reverse=True)
        setup.sweep = relevant[0]
        setup.reference_level = setup.sweep.pool.price
        setup.state = TSState.RECLAIM
        setup.notes.append(
            f"False break of {setup.sweep.pool.kind} @ {setup.reference_level:.5f}, "
            f"sweep extreme {setup.sweep.sweep_price:.5f}"
        )

        rel_disp = [d for d in displacements if d.direction == disp_dir and d.quality_score >= 50]
        if rel_disp:
            setup.displacement = rel_disp[-1]
            setup.state = TSState.DISPLACEMENT
            setup.notes.append(f"Displacement score {setup.displacement.quality_score}")
        else:
            setup.notes.append("Reclaim present but displacement not yet strong")

        # Entry: near the reclaimed level (slightly inside for BUY / SELL)
        if direction == "BUY":
            entry = setup.reference_level
            invalidation = setup.sweep.sweep_price
        else:
            entry = setup.reference_level
            invalidation = setup.sweep.sweep_price

        levels = build_trade_levels(
            direction=direction,
            symbol=symbol,
            current_price=current_price,
            entry_price=entry,
            entry_type="TURTLE_SOUP_RECLAIM",
            invalidation_price=invalidation,
            liquidity_pools=liquidity_pools,
            atr=atr,
            min_rr=min_rr,
        )
        setup.levels = levels

        if not levels.valid:
            setup.state = TSState.ENTRY_READY
            setup.notes.append(f"Levels rejected: {levels.rejection_reason}")
            results.append(setup)
            continue

        # Confirmation when price is back on the correct side of the level
        if direction == "BUY" and current_price > setup.reference_level:
            if setup.displacement and setup.displacement.quality_score >= 55:
                setup.state = TSState.CONFIRMED
                setup.formed_at = ts
                setup.notes.append("Reclaim + displacement — Turtle Soup CONFIRMED")
            else:
                setup.state = TSState.ENTRY_READY
                setup.notes.append("Reclaim confirmed — awaiting stronger displacement")
        elif direction == "SELL" and current_price < setup.reference_level:
            if setup.displacement and setup.displacement.quality_score >= 55:
                setup.state = TSState.CONFIRMED
                setup.formed_at = ts
                setup.notes.append("Reclaim + displacement — Turtle Soup CONFIRMED")
            else:
                setup.state = TSState.ENTRY_READY
                setup.notes.append("Reclaim confirmed — awaiting stronger displacement")
        else:
            setup.state = TSState.FALSE_BREAK
            setup.notes.append("Sweep occurred but reclaim not yet fully established")

        results.append(setup)

    return results
