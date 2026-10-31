"""
ICT Judas Swing Model

False initial directional move around a relevant session opening,
designed to raid liquidity before reversing toward the true objective.

Requires:
- Session context (London open / NY open preferred)
- Meaningful liquidity target raided
- Reversal evidence (reclaim + displacement / MSS)
- Opposing liquidity objective

Not every opening impulse is a Judas Swing.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Literal, Dict, Any
from enum import Enum

from ..liquidity import LiquiditySweep, LiquidityPool
from ..displacement import DisplacementEvent
from ..entry_risk import build_trade_levels, TradeLevels
from ..sessions import active_session_names, is_in_silver_bullet_window


class JudasState(str, Enum):
    IDLE = "IDLE"
    SESSION_OK = "SESSION_OK"
    FALSE_MOVE = "FALSE_MOVE"
    REVERSAL = "REVERSAL"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"


@dataclass
class JudasSetup:
    symbol: str
    direction: Literal["BUY", "SELL"]  # true direction after the fake move
    state: JudasState = JudasState.IDLE
    htf_bias: str = "neutral"
    session: Optional[str] = None
    sweep: Optional[LiquiditySweep] = None
    displacement: Optional[DisplacementEvent] = None
    levels: Optional[TradeLevels] = None
    score: float = 0.0
    notes: List[str] = field(default_factory=list)
    formed_at: Optional[str] = None
    last_updated: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": "ICT_Judas_Swing",
            "symbol": self.symbol,
            "direction": self.direction,
            "state": self.state.value,
            "htf_bias": self.htf_bias,
            "session": self.session,
            "setup_status": "CONFIRMED"
            if self.state == JudasState.CONFIRMED
            else "DEVELOPING"
            if self.state not in (JudasState.IDLE, JudasState.INVALIDATED)
            else "NO_SETUP",
            "score": self.score,
            "notes": self.notes,
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


def evaluate_judas(
    symbol: str,
    current_price: float,
    htf_bias: str,
    sweeps: List[LiquiditySweep],
    displacements: List[DisplacementEvent],
    liquidity_pools: List[LiquidityPool],
    atr: Optional[float] = None,
    min_rr: float = 2.0,
    now: Optional[datetime] = None,
) -> List[JudasSetup]:
    results: List[JudasSetup] = []
    ts = (now or datetime.now(timezone.utc)).isoformat()
    sessions = active_session_names(now)

    # Prefer London / NY open context
    relevant_sessions = [s for s in sessions if s in ("london", "newyork_am", "asian")]
    if not relevant_sessions:
        # Still allow evaluation but mark lower confidence
        session_label = "off_session"
    else:
        session_label = relevant_sessions[0]

    for direction, sweep_side, disp_dir in [
        ("BUY", "bullish", "bullish"),   # fake sell-off then buy
        ("SELL", "bearish", "bearish"), # fake rally then sell
    ]:
        setup = JudasSetup(
            symbol=symbol,
            direction=direction,
            htf_bias=htf_bias,
            session=session_label,
            last_updated=ts,
        )

        if session_label != "off_session":
            setup.state = JudasState.SESSION_OK
            setup.notes.append(f"Session context: {session_label}")
        else:
            setup.notes.append("Outside preferred Judas session windows — lower confidence")

        rel_sweeps = [
            s for s in sweeps
            if s.side == sweep_side and s.reclaim_confirmed and s.pool.strength >= 45
        ]
        if not rel_sweeps:
            setup.notes.append("No meaningful liquidity raid for Judas")
            results.append(setup)
            continue

        setup.sweep = sorted(rel_sweeps, key=lambda s: s.pool.strength, reverse=True)[0]
        setup.state = JudasState.FALSE_MOVE
        setup.notes.append(
            f"Judas raid of {setup.sweep.pool.kind} @ {setup.sweep.pool.price:.5f}, "
            f"extreme {setup.sweep.sweep_price:.5f}"
        )

        rel_disp = [
            d for d in displacements
            if d.direction == disp_dir and d.quality_score >= 55
        ]
        if not rel_disp:
            setup.notes.append("Raid seen but reversal displacement not confirmed")
            results.append(setup)
            continue

        setup.displacement = rel_disp[-1]
        setup.state = JudasState.REVERSAL
        setup.notes.append(f"Reversal displacement score {setup.displacement.quality_score}")

        entry = setup.sweep.pool.price  # reclaim level
        invalidation = setup.sweep.sweep_price

        levels = build_trade_levels(
            direction=direction,
            symbol=symbol,
            current_price=current_price,
            entry_price=entry,
            entry_type="JUDAS_RECLAIM",
            invalidation_price=invalidation,
            liquidity_pools=liquidity_pools,
            atr=atr,
            min_rr=min_rr,
        )
        setup.levels = levels

        if not levels.valid:
            setup.notes.append(f"Levels rejected: {levels.rejection_reason}")
            results.append(setup)
            continue

        # Confirm when price is back on the correct side of the raided level
        if direction == "BUY" and current_price > setup.sweep.pool.price:
            setup.state = JudasState.CONFIRMED
            setup.formed_at = ts
            setup.notes.append("Judas Swing CONFIRMED (signal-only)")
        elif direction == "SELL" and current_price < setup.sweep.pool.price:
            setup.state = JudasState.CONFIRMED
            setup.formed_at = ts
            setup.notes.append("Judas Swing CONFIRMED (signal-only)")
        else:
            setup.notes.append("Reversal in progress — entry pending full reclaim")

        results.append(setup)

    return results
