"""
ICT OTE (Optimal Trade Entry) — Location Model

OTE is a location model, not an independent entry signal.
It requires:
- Meaningful confirmed impulse dealing range
- Fib retracement into 62% / 70.5% / 79% zone
- Alignment with directional bias
- Liquidity event + POI / displacement or structure confirmation

Entry is taken inside the OTE band; SL beyond the impulse extreme;
TP is opposing liquidity.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Literal, Dict, Any
from enum import Enum

from ..premium_discount import DealingRange
from ..liquidity import LiquiditySweep, LiquidityPool
from ..displacement import DisplacementEvent
from ..fvg import FairValueGap, get_active_fvgs
from ..entry_risk import build_trade_levels, TradeLevels


class OTEState(str, Enum):
    IDLE = "IDLE"
    RANGE_OK = "RANGE_OK"
    IN_OTE_ZONE = "IN_OTE_ZONE"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"


@dataclass
class OTESetup:
    symbol: str
    direction: Literal["BUY", "SELL"]
    state: OTEState = OTEState.IDLE
    htf_bias: str = "neutral"
    ote_low: Optional[float] = None
    ote_high: Optional[float] = None
    fib_62: Optional[float] = None
    fib_705: Optional[float] = None
    fib_79: Optional[float] = None
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
            "model": "ICT_OTE",
            "symbol": self.symbol,
            "direction": self.direction,
            "state": self.state.value,
            "htf_bias": self.htf_bias,
            "setup_status": "CONFIRMED"
            if self.state == OTEState.CONFIRMED
            else "DEVELOPING"
            if self.state not in (OTEState.IDLE, OTEState.INVALIDATED)
            else "NO_SETUP",
            "score": self.score,
            "notes": self.notes,
            "ote_zone": {"low": self.ote_low, "high": self.ote_high},
            "fibs": {"62": self.fib_62, "70.5": self.fib_705, "79": self.fib_79},
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


def evaluate_ote(
    symbol: str,
    current_price: float,
    htf_bias: str,
    dealing_range: Optional[DealingRange],
    sweeps: List[LiquiditySweep],
    displacements: List[DisplacementEvent],
    fvgs: List[FairValueGap],
    liquidity_pools: List[LiquidityPool],
    atr: Optional[float] = None,
    min_rr: float = 2.0,
) -> List[OTESetup]:
    results: List[OTESetup] = []
    ts = datetime.now(timezone.utc).isoformat()

    if dealing_range is None:
        return results

    high, low = dealing_range.high, dealing_range.low
    rng = high - low
    if rng <= 0:
        return results

    # Standard OTE bands measured from the impulse extreme
    # Bullish OTE: retracement from high toward low → 62-79% from high
    # Bearish OTE: retracement from low toward high → 62-79% from low

    for direction in ("BUY", "SELL"):
        setup = OTESetup(
            symbol=symbol,
            direction=direction,
            htf_bias=htf_bias,
            last_updated=ts,
        )

        if direction == "BUY":
            # Prefer discount / bullish bias
            fib62 = high - rng * 0.62
            fib705 = high - rng * 0.705
            fib79 = high - rng * 0.79
            ote_low, ote_high = fib79, fib62
            invalidation = low
            preferred_bias = "bullish"
        else:
            fib62 = low + rng * 0.62
            fib705 = low + rng * 0.705
            fib79 = low + rng * 0.79
            ote_low, ote_high = fib62, fib79
            invalidation = high
            preferred_bias = "bearish"

        setup.fib_62, setup.fib_705, setup.fib_79 = fib62, fib705, fib79
        setup.ote_low, setup.ote_high = ote_low, ote_high
        setup.state = OTEState.RANGE_OK
        setup.notes.append(f"OTE band {ote_low:.5f} – {ote_high:.5f}")

        in_zone = ote_low <= current_price <= ote_high
        if not in_zone:
            setup.notes.append("Price not inside OTE zone")
            results.append(setup)
            continue

        setup.state = OTEState.IN_OTE_ZONE
        setup.notes.append("Price inside OTE zone")

        # Require at least one supporting factor: sweep, displacement, or FVG
        sweep_side = "bullish" if direction == "BUY" else "bearish"
        rel_sweeps = [s for s in sweeps if s.side == sweep_side and s.reclaim_confirmed]
        rel_disp = [
            d for d in displacements
            if d.direction == ("bullish" if direction == "BUY" else "bearish")
            and d.quality_score >= 50
        ]
        rel_fvg = get_active_fvgs(fvgs, current_price, direction=("bullish" if direction == "BUY" else "bearish"))

        support = 0
        if rel_sweeps:
            setup.sweep = rel_sweeps[-1]
            support += 1
            setup.notes.append("Supporting liquidity sweep")
        if rel_disp:
            setup.displacement = rel_disp[-1]
            support += 1
            setup.notes.append(f"Supporting displacement {setup.displacement.quality_score}")
        if rel_fvg:
            setup.fvg = rel_fvg[0]
            support += 1
            setup.notes.append("Supporting FVG in zone")

        if htf_bias == preferred_bias:
            support += 1
            setup.notes.append("HTF bias aligned")
        elif htf_bias not in ("neutral", preferred_bias):
            setup.notes.append("HTF bias counter — reduced confluence")

        if support < 2:
            setup.notes.append("Insufficient confirmation for OTE entry (need ≥2 factors)")
            results.append(setup)
            continue

        # Entry at 70.5% (classic) or midpoint of band
        entry = setup.fib_705 if setup.fib_705 else (ote_low + ote_high) / 2.0

        levels = build_trade_levels(
            direction=direction,
            symbol=symbol,
            current_price=current_price,
            entry_price=entry,
            entry_type="OTE_70.5",
            invalidation_price=invalidation,
            liquidity_pools=liquidity_pools,
            atr=atr,
            min_rr=min_rr,
            entry_zone_low=ote_low,
            entry_zone_high=ote_high,
        )
        setup.levels = levels

        if not levels.valid:
            setup.notes.append(f"Levels rejected: {levels.rejection_reason}")
            results.append(setup)
            continue

        setup.state = OTEState.CONFIRMED
        setup.formed_at = ts
        setup.notes.append("OTE location + confirmations — CONFIRMED (signal-only)")
        results.append(setup)

    return results
