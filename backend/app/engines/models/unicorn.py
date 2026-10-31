"""
ICT Unicorn Model — State Machine

Sequence:
1. Valid liquidity raid (sweep)
2. Displacement + MSS / structure shift
3. Relevant breaker block (failed OB that flips)
4. Overlapping FVG (confluence zone)
5. Retracement into the Unicorn entry zone (breaker + FVG overlap)
6. Structural SL + opposing liquidity target

Ordinary OB/FVG overlap without the structural context is NOT a Unicorn.
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
from ..entry_risk import build_trade_levels, TradeLevels


class UnicornState(str, Enum):
    IDLE = "IDLE"
    SWEEP = "SWEEP"
    DISPLACEMENT = "DISPLACEMENT"
    BREAKER_FOUND = "BREAKER_FOUND"
    FVG_CONFLUENCE = "FVG_CONFLUENCE"
    ENTRY_READY = "ENTRY_READY"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"


@dataclass
class UnicornSetup:
    symbol: str
    direction: Literal["BUY", "SELL"]
    state: UnicornState = UnicornState.IDLE
    htf_bias: str = "neutral"
    sweep: Optional[LiquiditySweep] = None
    displacement: Optional[DisplacementEvent] = None
    breaker: Optional[OrderBlock] = None
    fvg: Optional[FairValueGap] = None
    confluence_low: Optional[float] = None
    confluence_high: Optional[float] = None
    levels: Optional[TradeLevels] = None
    score: float = 0.0
    notes: List[str] = field(default_factory=list)
    formed_at: Optional[str] = None
    last_updated: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": "ICT_Unicorn",
            "symbol": self.symbol,
            "direction": self.direction,
            "state": self.state.value,
            "htf_bias": self.htf_bias,
            "setup_status": "CONFIRMED"
            if self.state == UnicornState.CONFIRMED
            else "DEVELOPING"
            if self.state not in (UnicornState.IDLE, UnicornState.INVALIDATED)
            else "NO_SETUP",
            "score": self.score,
            "notes": self.notes,
            "confluence_zone": {
                "low": self.confluence_low,
                "high": self.confluence_high,
            }
            if self.confluence_low is not None
            else None,
            "breaker": {
                "high": self.breaker.high,
                "low": self.breaker.low,
                "midpoint": self.breaker.midpoint,
                "quality": self.breaker.quality,
            }
            if self.breaker
            else None,
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


def _overlap(a_low: float, a_high: float, b_low: float, b_high: float) -> Optional[tuple[float, float]]:
    low = max(a_low, b_low)
    high = min(a_high, b_high)
    if low < high:
        return low, high
    return None


def evaluate_unicorn(
    symbol: str,
    current_price: float,
    htf_bias: str,
    sweeps: List[LiquiditySweep],
    displacements: List[DisplacementEvent],
    fvgs: List[FairValueGap],
    order_blocks: List[OrderBlock],
    liquidity_pools: List[LiquidityPool],
    atr: Optional[float] = None,
    min_rr: float = 2.0,
) -> List[UnicornSetup]:
    results: List[UnicornSetup] = []
    ts = datetime.now(timezone.utc).isoformat()

    breakers = [ob for ob in order_blocks if ob.is_breaker or ob.invalidated]

    for direction, sweep_side, fvg_dir, disp_dir, breaker_dir in [
        ("BUY", "bullish", "bullish", "bullish", "bearish"),  # bullish unicorn often uses former bearish OB as breaker
        ("SELL", "bearish", "bearish", "bearish", "bullish"),
    ]:
        setup = UnicornSetup(
            symbol=symbol,
            direction=direction,
            htf_bias=htf_bias,
            last_updated=ts,
        )

        relevant_sweeps = [s for s in sweeps if s.side == sweep_side and s.reclaim_confirmed]
        if not relevant_sweeps:
            setup.notes.append("No confirmed liquidity raid")
            results.append(setup)
            continue
        setup.sweep = relevant_sweeps[-1]
        setup.state = UnicornState.SWEEP
        setup.notes.append(f"Liquidity raid @ {setup.sweep.sweep_price}")

        rel_disp = [d for d in displacements if d.direction == disp_dir and d.quality_score >= 55]
        if not rel_disp:
            setup.notes.append("No qualifying displacement")
            results.append(setup)
            continue
        setup.displacement = rel_disp[-1]
        setup.state = UnicornState.DISPLACEMENT

        # Prefer invalidated OBs of opposite colour as breakers
        cand_breakers = [
            b for b in breakers
            if b.direction == breaker_dir or b.is_breaker
        ]
        if not cand_breakers:
            # fallback: any high-quality OB that has been mitigated heavily
            cand_breakers = [b for b in order_blocks if b.mitigation_pct > 0.8 and b.quality >= 50]
        if not cand_breakers:
            setup.notes.append("No breaker block found")
            results.append(setup)
            continue
        setup.breaker = sorted(cand_breakers, key=lambda x: x.quality, reverse=True)[0]
        setup.state = UnicornState.BREAKER_FOUND
        setup.notes.append(f"Breaker {setup.breaker.low:.5f}-{setup.breaker.high:.5f}")

        active = get_active_fvgs(fvgs, current_price, direction=fvg_dir)
        if not active:
            setup.notes.append("No active FVG for confluence")
            results.append(setup)
            continue

        # Find FVG that overlaps the breaker
        overlap = None
        chosen_fvg = None
        for fvg in active:
            ov = _overlap(setup.breaker.low, setup.breaker.high, fvg.lower, fvg.upper)
            if ov:
                overlap = ov
                chosen_fvg = fvg
                break

        if not overlap or not chosen_fvg:
            setup.notes.append("No breaker + FVG overlap (required for Unicorn)")
            results.append(setup)
            continue

        setup.fvg = chosen_fvg
        setup.confluence_low, setup.confluence_high = overlap
        setup.state = UnicornState.FVG_CONFLUENCE
        setup.notes.append(
            f"Unicorn zone {setup.confluence_low:.5f}-{setup.confluence_high:.5f}"
        )

        entry = (setup.confluence_low + setup.confluence_high) / 2.0
        invalidation = (
            min(setup.sweep.sweep_price, setup.confluence_low)
            if direction == "BUY"
            else max(setup.sweep.sweep_price, setup.confluence_high)
        )

        levels = build_trade_levels(
            direction=direction,
            symbol=symbol,
            current_price=current_price,
            entry_price=entry,
            entry_type="UNICORN_CONFLUENCE",
            invalidation_price=invalidation,
            liquidity_pools=liquidity_pools,
            atr=atr,
            min_rr=min_rr,
            entry_zone_low=setup.confluence_low,
            entry_zone_high=setup.confluence_high,
        )
        setup.levels = levels

        if not levels.valid:
            setup.state = UnicornState.ENTRY_READY
            setup.notes.append(f"Levels rejected: {levels.rejection_reason}")
            results.append(setup)
            continue

        in_zone = setup.confluence_low <= current_price <= setup.confluence_high
        if in_zone or abs(current_price - entry) / entry < 0.0008:
            setup.state = UnicornState.CONFIRMED
            setup.formed_at = ts
            setup.notes.append("Price in Unicorn zone — CONFIRMED (signal-only)")
        else:
            setup.state = UnicornState.ENTRY_READY
            setup.notes.append("Unicorn zone ready — waiting for retracement")

        results.append(setup)

    return results
