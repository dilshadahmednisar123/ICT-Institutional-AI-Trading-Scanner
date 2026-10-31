"""
ICT Silver Bullet Model — State Machine

Only valid inside the designated New York time windows:
- 03:00–04:00 NY
- 10:00–11:00 NY
- 14:00–15:00 NY

Bullish sequence:
1. HTF bullish context (preferred)
2. Sell-side liquidity swept
3. Bullish displacement
4. Bullish MSS / structure shift
5. Bullish FVG forms
6. Price retraces into FVG → entry
7. Target opposing buy-side liquidity

Bearish is the inverse.
Outside the SB windows the model returns no setup.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Literal, Dict, Any
from enum import Enum

from ..fvg import FairValueGap, get_active_fvgs
from ..liquidity import LiquiditySweep, LiquidityPool
from ..displacement import DisplacementEvent
from ..order_blocks import OrderBlock
from ..entry_risk import build_trade_levels, choose_entry_from_fvg, TradeLevels
from ..premium_discount import DealingRange
from ..sessions import is_in_silver_bullet_window, session_score


class SBState(str, Enum):
    OUTSIDE_WINDOW = "OUTSIDE_WINDOW"
    IDLE = "IDLE"
    SWEEP = "SWEEP"
    DISPLACEMENT = "DISPLACEMENT"
    FVG_READY = "FVG_READY"
    ENTRY_READY = "ENTRY_READY"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"


@dataclass
class SilverBulletSetup:
    symbol: str
    direction: Literal["BUY", "SELL"]
    state: SBState = SBState.IDLE
    window_label: Optional[str] = None
    htf_bias: str = "neutral"
    sweep: Optional[LiquiditySweep] = None
    displacement: Optional[DisplacementEvent] = None
    fvg: Optional[FairValueGap] = None
    levels: Optional[TradeLevels] = None
    score: float = 0.0
    notes: List[str] = field(default_factory=list)
    formed_at: Optional[str] = None
    last_updated: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": "ICT_Silver_Bullet",
            "symbol": self.symbol,
            "direction": self.direction,
            "state": self.state.value,
            "window": self.window_label,
            "htf_bias": self.htf_bias,
            "setup_status": "CONFIRMED"
            if self.state == SBState.CONFIRMED
            else "DEVELOPING"
            if self.state not in (SBState.IDLE, SBState.OUTSIDE_WINDOW, SBState.INVALIDATED)
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
            "fvg": {
                "upper": self.fvg.upper,
                "lower": self.fvg.lower,
                "midpoint": self.fvg.midpoint,
            }
            if self.fvg
            else None,
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


def evaluate_silver_bullet(
    symbol: str,
    current_price: float,
    htf_bias: str,
    sweeps: List[LiquiditySweep],
    displacements: List[DisplacementEvent],
    fvgs: List[FairValueGap],
    liquidity_pools: List[LiquidityPool],
    atr: Optional[float] = None,
    min_rr: float = 0.0,
    now: Optional[datetime] = None,
) -> List[SilverBulletSetup]:
    results: List[SilverBulletSetup] = []
    ts = (now or datetime.now(timezone.utc)).isoformat()

    in_window, window_label = is_in_silver_bullet_window(now)
    if not in_window:
        # Explicitly return a single OUTSIDE_WINDOW marker so callers know why
        setup = SilverBulletSetup(
            symbol=symbol,
            direction="BUY",
            state=SBState.OUTSIDE_WINDOW,
            notes=["Outside Silver Bullet windows — model inactive"],
            last_updated=ts,
        )
        results.append(setup)
        return results

    for direction, sweep_side, fvg_dir, disp_dir in [
        ("BUY", "bullish", "bullish", "bullish"),
        ("SELL", "bearish", "bearish", "bearish"),
    ]:
        setup = SilverBulletSetup(
            symbol=symbol,
            direction=direction,
            window_label=window_label,
            htf_bias=htf_bias,
            last_updated=ts,
        )
        setup.notes.append(f"Inside Silver Bullet window: {window_label}")

        # Sweep
        relevant = [s for s in sweeps if s.side == sweep_side and s.reclaim_confirmed]
        if not relevant:
            setup.notes.append("No confirmed liquidity sweep")
            results.append(setup)
            continue
        setup.sweep = relevant[-1]
        setup.state = SBState.SWEEP
        setup.notes.append(f"Sweep @ {setup.sweep.sweep_price}")

        # Displacement
        rel_disp = [d for d in displacements if d.direction == disp_dir and d.quality_score >= 55]
        if not rel_disp:
            setup.notes.append("No qualifying displacement")
            results.append(setup)
            continue
        setup.displacement = rel_disp[-1]
        setup.state = SBState.DISPLACEMENT
        setup.notes.append(f"Displacement score {setup.displacement.quality_score}")

        # FVG
        active = get_active_fvgs(fvgs, current_price, direction=fvg_dir)
        if not active:
            setup.notes.append("No active FVG")
            results.append(setup)
            continue
        setup.fvg = active[0]
        setup.state = SBState.FVG_READY
        setup.notes.append(f"FVG {setup.fvg.lower:.5f}-{setup.fvg.upper:.5f}")

        # Levels
        entry, etype, zlow, zhigh = choose_entry_from_fvg(setup.fvg, "midpoint")
        invalidation = (
            min(setup.sweep.sweep_price, setup.fvg.lower)
            if direction == "BUY"
            else max(setup.sweep.sweep_price, setup.fvg.upper)
        )
        levels = build_trade_levels(
            direction=direction,
            symbol=symbol,
            current_price=current_price,
            entry_price=entry,
            entry_type=etype,
            invalidation_price=invalidation,
            liquidity_pools=liquidity_pools,
            atr=atr,
            min_rr=min_rr,
            entry_zone_low=zlow,
            entry_zone_high=zhigh,
        )
        setup.levels = levels

        if not levels.valid:
            setup.state = SBState.ENTRY_READY
            setup.notes.append(f"Levels rejected: {levels.rejection_reason}")
            results.append(setup)
            continue

        in_zone = zlow <= current_price <= zhigh
        if in_zone or abs(current_price - entry) / entry < 0.0008:
            setup.state = SBState.CONFIRMED
            setup.formed_at = ts
            setup.notes.append("Price in entry zone — Silver Bullet CONFIRMED (signal-only)")
        else:
            setup.state = SBState.ENTRY_READY
            setup.notes.append("Entry zone ready — waiting for retracement")

        results.append(setup)

    return results
