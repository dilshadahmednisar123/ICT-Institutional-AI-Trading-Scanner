"""
ICT 2022 Mentorship Model — State Machine

Bullish sequence (strict):
1. HTF bullish context / bias
2. Identify liquidity draw (SSL)
3. Price reaches relevant discount POI (optional but preferred)
4. Sell-side liquidity is swept
5. Bullish displacement occurs
6. Bullish MSS / BOS confirmed
7. Valid bullish FVG forms
8. Price retraces into the FVG (entry zone)
9. Entry confirmed → structural SL + opposing BSL target

Bearish is the exact inverse.

A setup is only CONFIRMED when the full mandatory sequence is present.
Developing setups are tracked but never presented as executable trades.
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
from ..structure import StructureEvent


class ModelState(str, Enum):
    IDLE = "IDLE"
    HTF_BIAS_OK = "HTF_BIAS_OK"
    LIQUIDITY_IDENTIFIED = "LIQUIDITY_IDENTIFIED"
    SWEEP_OCCURRED = "SWEEP_OCCURRED"
    DISPLACEMENT = "DISPLACEMENT"
    MSS_CONFIRMED = "MSS_CONFIRMED"
    FVG_FORMED = "FVG_FORMED"
    ENTRY_ZONE_READY = "ENTRY_ZONE_READY"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"


@dataclass
class ICT2022Setup:
    symbol: str
    direction: Literal["BUY", "SELL"]
    state: ModelState = ModelState.IDLE
    htf_bias: str = "neutral"
    sweep: Optional[LiquiditySweep] = None
    displacement: Optional[DisplacementEvent] = None
    fvg: Optional[FairValueGap] = None
    order_block: Optional[OrderBlock] = None
    dealing_range: Optional[DealingRange] = None
    premium_discount: Optional[str] = None
    levels: Optional[TradeLevels] = None
    score: float = 0.0
    notes: List[str] = field(default_factory=list)
    formed_at: Optional[str] = None
    last_updated: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": "ICT_2022_Mentorship",
            "symbol": self.symbol,
            "direction": self.direction,
            "state": self.state.value,
            "htf_bias": self.htf_bias,
            "setup_status": "CONFIRMED"
            if self.state == ModelState.CONFIRMED
            else "DEVELOPING"
            if self.state not in (ModelState.IDLE, ModelState.INVALIDATED)
            else "NO_SETUP",
            "score": self.score,
            "notes": self.notes,
            "sweep": {
                "side": self.sweep.side,
                "classification": self.sweep.classification,
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
                "direction": self.fvg.direction,
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
                "tp3": self.levels.take_profit_3,
                "primary_tp": self.levels.primary_tp,
                "risk_reward": self.levels.risk_reward,
                "valid": self.levels.valid,
                "rejection_reason": self.levels.rejection_reason,
            }
            if self.levels
            else None,
            "premium_discount": self.premium_discount,
            "formed_at": self.formed_at,
            "last_updated": self.last_updated,
        }


def evaluate_ict_2022(
    symbol: str,
    current_price: float,
    htf_bias: str,
    sweeps: List[LiquiditySweep],
    displacements: List[DisplacementEvent],
    fvgs: List[FairValueGap],
    order_blocks: List[OrderBlock],
    liquidity_pools: List[LiquidityPool],
    dealing_range: Optional[DealingRange],
    premium_discount: Optional[str],
    atr: Optional[float] = None,
    min_rr: float = 0.0,
    structure_events: Optional[List[StructureEvent]] = None,
) -> List[ICT2022Setup]:
    """
    Evaluate possible ICT 2022 setups for both directions.
    Returns zero or more setups (usually 0 or 1).
    """
    results: List[ICT2022Setup] = []
    now = datetime.now(timezone.utc).isoformat()

    for direction, bias_needed, sweep_side, fvg_dir, disp_dir in [
        ("BUY", "bullish", "bullish", "bullish", "bullish"),
        ("SELL", "bearish", "bearish", "bearish", "bearish"),
    ]:
        setup = ICT2022Setup(
            symbol=symbol,
            direction=direction,
            htf_bias=htf_bias,
            dealing_range=dealing_range,
            premium_discount=premium_discount,
            last_updated=now,
        )

        # 1. HTF Bias
        if htf_bias != bias_needed:
            setup.notes.append(f"HTF bias {htf_bias} is not aligned with required {bias_needed}")
            results.append(setup)
            continue
        setup.state = ModelState.HTF_BIAS_OK
        setup.notes.append(f"HTF bias aligned ({htf_bias})")

        # 2+3. Liquidity sweep of correct side
        relevant_sweeps = [s for s in sweeps if s.side == sweep_side and s.reclaim_confirmed and s.time is not None]
        if not relevant_sweeps:
            setup.notes.append("No confirmed liquidity sweep of required side")
            results.append(setup)
            continue

        setup.sweep = relevant_sweeps[-1]
        setup.state = ModelState.SWEEP_OCCURRED
        setup.notes.append(f"Confirmed {sweep_side} liquidity sweep @ {setup.sweep.sweep_price}")

        # 4. Displacement
        relevant_disp = [
            d for d in displacements
            if d.direction == disp_dir and d.quality_score >= 55 and d.time >= setup.sweep.time
        ]
        if not relevant_disp:
            setup.notes.append("No qualifying displacement after sweep")
            results.append(setup)
            continue

        setup.displacement = relevant_disp[-1]
        setup.state = ModelState.DISPLACEMENT
        setup.notes.append(f"Displacement quality {setup.displacement.quality_score}")

        # Require a close-confirmed structure break after both the sweep and displacement.
        post_sweep_structure = [
            event for event in (structure_events or [])
            if event.direction == disp_dir
            and event.event_type in ("BOS", "CHOCH", "MSS")
            and event.confirmed_by_close
            and event.time >= setup.sweep.time
            and event.time >= setup.displacement.time
        ]
        if not post_sweep_structure:
            setup.notes.append("No close-confirmed BOS/CHOCH after sweep and displacement")
            results.append(setup)
            continue
        setup.notes.append(f"Structure shift confirmed: {post_sweep_structure[-1].event_type}")

        matching_obs = [ob for ob in order_blocks if ob.direction == fvg_dir and not ob.invalidated]
        if matching_obs:
            setup.order_block = matching_obs[-1]

        # 5. Prefer also having an FVG created by the move
        active = [
            fvg for fvg in get_active_fvgs(fvgs, current_price, direction=fvg_dir)
            if fvg.formation_time >= setup.displacement.time
        ]
        if not active:
            setup.notes.append("No active FVG in the required direction")
            results.append(setup)
            continue

        setup.fvg = active[0]
        setup.state = ModelState.FVG_FORMED
        setup.notes.append(
            f"Active {fvg_dir} FVG {setup.fvg.lower:.5f} – {setup.fvg.upper:.5f}"
        )

        # Premium/Discount preference
        if direction == "BUY" and premium_discount == "premium":
            setup.notes.append("BUY in premium — reduced confluence")
        if direction == "SELL" and premium_discount == "discount":
            setup.notes.append("SELL in discount — reduced confluence")

        # Entry calculation
        entry_price, entry_type, zlow, zhigh = choose_entry_from_fvg(setup.fvg, preference="midpoint")

        # Invalidation = swept liquidity extreme or FVG distal
        if direction == "BUY":
            invalidation = min(setup.sweep.sweep_price, setup.fvg.lower)
        else:
            invalidation = max(setup.sweep.sweep_price, setup.fvg.upper)

        levels = build_trade_levels(
            direction=direction,
            symbol=symbol,
            current_price=current_price,
            entry_price=entry_price,
            entry_type=entry_type,
            invalidation_price=invalidation,
            liquidity_pools=liquidity_pools,
            atr=atr,
            min_rr=min_rr,
            entry_zone_low=zlow,
            entry_zone_high=zhigh,
        )
        setup.levels = levels

        if not levels.valid:
            setup.state = ModelState.ENTRY_ZONE_READY
            setup.notes.append(f"Levels calculated but rejected: {levels.rejection_reason}")
            results.append(setup)
            continue

        # If price has not yet returned to the FVG we stay in ENTRY_ZONE_READY (pending)
        in_zone = zlow <= current_price <= zhigh
        if in_zone or abs(current_price - entry_price) / entry_price < 0.0008:
            setup.state = ModelState.CONFIRMED
            setup.formed_at = now
            setup.notes.append("Price interacting with entry zone — CONFIRMED (signal-only)")
        else:
            setup.state = ModelState.ENTRY_ZONE_READY
            setup.notes.append("Entry zone ready — waiting for price to return (DEVELOPING)")

        results.append(setup)

    return results
