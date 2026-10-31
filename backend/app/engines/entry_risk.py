"""
Precise Entry / Structural Stop-Loss / Liquidity-Based Take-Profit Engine

Rules enforced:
- Entry is never arbitrary.
- Stop is always structural (beyond invalidation).
- Take-profit is always a real liquidity pool.
- RR is calculated mathematically and reported; no minimum RR is imposed unless configured.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Literal, Tuple
from datetime import datetime, timezone

from .fvg import FairValueGap
from .order_blocks import OrderBlock
from .liquidity import LiquidityPool, rank_targets
from .premium_discount import DealingRange


@dataclass
class TradeLevels:
    direction: Literal["BUY", "SELL"]
    entry_price: float
    entry_type: str  # FVG_MIDPOINT, FVG_PROXIMAL, OB_MIDPOINT, OB_PROXIMAL, BREAKER, MARKET
    stop_loss: float
    stop_reason: str
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    tp1_type: Optional[str] = None
    tp2_type: Optional[str] = None
    tp3_type: Optional[str] = None
    primary_tp: Optional[float] = None
    risk: float = 0.0
    reward: float = 0.0
    risk_reward: float = 0.0
    buffer_used: float = 0.0
    valid: bool = False
    rejection_reason: Optional[str] = None
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None


def _pip_size(symbol: str) -> float:
    """Rough pip/point size helper."""
    s = symbol.upper()
    if "XAU" in s or "GOLD" in s:
        return 0.1
    if "XAG" in s:
        return 0.01
    if "JPY" in s:
        return 0.01
    return 0.0001


def calculate_structural_stop(
    direction: Literal["BUY", "SELL"],
    invalidation_price: float,
    symbol: str,
    atr: Optional[float] = None,
    spread: float = 0.0,
    buffer_atr_mult: float = 0.15,
    min_buffer_pips: float = 2.0,
) -> Tuple[float, float]:
    """
    Place stop beyond structural invalidation with a small volatility-aware buffer.
    Returns (stop_price, buffer_used).
    """
    pip = _pip_size(symbol)
    buffer = max(min_buffer_pips * pip, (atr or 0.0) * buffer_atr_mult)
    buffer = max(buffer, spread * 1.5)  # at least cover spread-ish

    if direction == "BUY":
        stop = invalidation_price - buffer
    else:
        stop = invalidation_price + buffer

    return stop, buffer


def choose_entry_from_fvg(
    fvg: FairValueGap,
    preference: str = "midpoint",
) -> Tuple[float, str, float, float]:
    """
    Returns entry_price, entry_type, zone_low, zone_high.
    """
    if preference == "proximal":
        if fvg.direction == "bullish":
            return fvg.upper, "FVG_PROXIMAL", fvg.lower, fvg.upper
        else:
            return fvg.lower, "FVG_PROXIMAL", fvg.lower, fvg.upper
    if preference == "distal":
        if fvg.direction == "bullish":
            return fvg.lower, "FVG_DISTAL", fvg.lower, fvg.upper
        else:
            return fvg.upper, "FVG_DISTAL", fvg.lower, fvg.upper
    # default midpoint (CE)
    return fvg.midpoint, "FVG_MIDPOINT", fvg.lower, fvg.upper


def choose_entry_from_ob(
    ob: OrderBlock,
    preference: str = "midpoint",
) -> Tuple[float, str, float, float]:
    if preference == "proximal":
        price = ob.proximal
        etype = "OB_PROXIMAL"
    elif preference == "distal":
        price = ob.distal
        etype = "OB_DISTAL"
    else:
        price = ob.midpoint
        etype = "OB_MIDPOINT"
    return price, etype, ob.low, ob.high


def build_trade_levels(
    direction: Literal["BUY", "SELL"],
    symbol: str,
    current_price: float,
    entry_price: float,
    entry_type: str,
    invalidation_price: float,
    liquidity_pools: List[LiquidityPool],
    atr: Optional[float] = None,
    spread: float = 0.0,
    min_rr: float = 0.0,
    entry_zone_low: Optional[float] = None,
    entry_zone_high: Optional[float] = None,
) -> TradeLevels:
    """
    Construct complete trade levels; RR is reported and only filtered when min_rr > 0.
    """
    stop, buffer = calculate_structural_stop(
        direction=direction,
        invalidation_price=invalidation_price,
        symbol=symbol,
        atr=atr,
        spread=spread,
    )

    # Rank opposing liquidity
    targets = rank_targets(liquidity_pools, current_price if current_price else entry_price, direction, max_targets=5)

    tp1 = tp2 = tp3 = None
    tp1_type = tp2_type = tp3_type = None

    if len(targets) >= 1:
        tp1 = targets[0].price
        tp1_type = targets[0].kind
    if len(targets) >= 2:
        tp2 = targets[1].price
        tp2_type = targets[1].kind
    if len(targets) >= 3:
        tp3 = targets[2].price
        tp3_type = targets[2].kind

    primary = tp1 or tp2  # target the nearest highest-ranked opposing liquidity pool

    # Calculate risk / reward
    if direction == "BUY":
        risk = entry_price - stop
        reward = (primary - entry_price) if primary else 0.0
    else:
        risk = stop - entry_price
        reward = (entry_price - primary) if primary else 0.0

    rr = reward / risk if risk > 0 else 0.0

    valid = True
    reason = None

    if risk <= 0:
        valid = False
        reason = "Invalid risk (stop on wrong side of entry)"
    elif primary is None:
        valid = False
        reason = "No opposing liquidity target found"
    elif rr < min_rr:
        valid = False
        reason = f"RR {rr:.2f} below minimum {min_rr}"
    elif direction == "BUY" and not (stop < entry_price < (primary or entry_price + 1)):
        valid = False
        reason = "Price ordering invalid for BUY"
    elif direction == "SELL" and not ((primary or entry_price - 1) < entry_price < stop):
        valid = False
        reason = "Price ordering invalid for SELL"

    return TradeLevels(
        direction=direction,
        entry_price=round(entry_price, 5),
        entry_type=entry_type,
        stop_loss=round(stop, 5),
        stop_reason=f"Structural invalidation beyond {invalidation_price:.5f} + buffer",
        take_profit_1=round(tp1, 5) if tp1 else None,
        take_profit_2=round(tp2, 5) if tp2 else None,
        take_profit_3=round(tp3, 5) if tp3 else None,
        tp1_type=tp1_type,
        tp2_type=tp2_type,
        tp3_type=tp3_type,
        primary_tp=round(primary, 5) if primary else None,
        risk=round(risk, 5),
        reward=round(reward, 5),
        risk_reward=round(rr, 2),
        buffer_used=round(buffer, 5),
        valid=valid,
        rejection_reason=reason,
        entry_zone_low=entry_zone_low,
        entry_zone_high=entry_zone_high,
    )
