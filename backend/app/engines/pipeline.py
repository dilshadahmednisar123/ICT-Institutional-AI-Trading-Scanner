"""
Core Analysis Pipeline

Runs the deterministic ICT engines in sequence and produces a structured result.
This is the heart of the scanner. Models will later plug into this pipeline.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Literal
import logging
import pandas as pd

from ..data.provider import BaseDataProvider, get_provider, DataQualityReport
from .structure import find_swing_points, classify_structure, detect_bos_choch
from .fvg import detect_fvgs, get_active_fvgs
from .liquidity import build_liquidity_map, detect_sweeps, rank_targets
from .displacement import detect_displacement
from .premium_discount import build_dealing_range

logger = logging.getLogger("ict_scanner.pipeline")


@dataclass
class AnalysisResult:
    symbol: str
    timeframe: str
    timestamp_utc: str
    data_quality: Dict[str, Any]
    current_price: Optional[float]
    bias: str
    dealing_range: Optional[Dict[str, Any]]
    premium_discount: Optional[str]
    swings_count: int
    fvgs: List[Dict[str, Any]] = field(default_factory=list)
    active_fvgs: List[Dict[str, Any]] = field(default_factory=list)
    liquidity_pools: List[Dict[str, Any]] = field(default_factory=list)
    sweeps: List[Dict[str, Any]] = field(default_factory=list)
    displacements: List[Dict[str, Any]] = field(default_factory=list)
    structure_events: List[Dict[str, Any]] = field(default_factory=list)
    setup_status: Literal["NO_SETUP", "DEVELOPING", "CONFIRMED", "INVALIDATED"] = "NO_SETUP"
    notes: List[str] = field(default_factory=list)
    error: Optional[str] = None


def analyze_symbol(
    symbol: str,
    timeframe: str = "15M",
    provider: Optional[BaseDataProvider] = None,
    limit: int = 400,
) -> AnalysisResult:
    """
    Full deterministic analysis pass for one symbol + timeframe.
    """
    provider = provider or get_provider("dukascopy")
    now = datetime.now(timezone.utc).isoformat()

    try:
        df = provider.get_ohlc(symbol, timeframe, limit=limit)
        quality = provider.validate(df, symbol, timeframe)

        if not quality.is_valid or df is None or df.empty:
            return AnalysisResult(
                symbol=symbol,
                timeframe=timeframe,
                timestamp_utc=now,
                data_quality=asdict(quality),
                current_price=None,
                bias="unknown",
                dealing_range=None,
                premium_discount=None,
                swings_count=0,
                setup_status="NO_SETUP",
                notes=["DATA UNAVAILABLE or invalid"],
                error=quality.message,
            )

        current_price = float(df.iloc[-1]["close"])

        # Structure
        swings = find_swing_points(df, left=3, right=3, strength="short")
        structure = classify_structure(swings)
        bos_events = detect_bos_choch(df, swings, timeframe=timeframe)

        # Dealing range & premium/discount
        dealing = build_dealing_range(swings)
        pd_class = dealing.classify(current_price) if dealing else None

        # FVGs
        fvgs = detect_fvgs(df, timeframe=timeframe)
        active = get_active_fvgs(fvgs, current_price)

        # Liquidity
        pools = build_liquidity_map(df, swings, timeframe=timeframe)
        sweeps = detect_sweeps(df, pools)

        # Displacement
        displacements = detect_displacement(df)

        notes = []
        status: Literal["NO_SETUP", "DEVELOPING", "CONFIRMED", "INVALIDATED"] = "NO_SETUP"

        # Very basic developing / confirmed heuristics (full models come later)
        recent_sweeps = [s for s in sweeps if s.reclaim_confirmed]
        recent_disp = [d for d in displacements if d.quality_score >= 65][-3:]

        if recent_sweeps and recent_disp and active:
            # Potential developing setup
            status = "DEVELOPING"
            notes.append("Liquidity sweep + displacement + active FVG detected → developing setup")
            notes.append("Full model confirmation (MSS + entry trigger) still required before CONFIRMED")
        elif recent_sweeps:
            notes.append("Liquidity sweep observed but missing displacement or FVG")
        else:
            notes.append("No qualifying ICT sequence — NO TRADE")

        def ser_fvg(f):
            return {
                "direction": f.direction,
                "upper": f.upper,
                "lower": f.lower,
                "midpoint": f.midpoint,
                "width": f.width,
                "timeframe": f.timeframe,
                "mitigated_pct": f.mitigated_pct,
                "is_filled": f.is_filled,
            }

        def ser_pool(p):
            return {
                "price": p.price,
                "side": p.side,
                "kind": p.kind,
                "strength": p.strength,
                "touches": p.touches,
                "swept": p.swept,
            }

        def ser_sweep(s):
            return {
                "side": s.side,
                "classification": s.classification,
                "sweep_price": s.sweep_price,
                "pool_price": s.pool.price,
                "pool_kind": s.pool.kind,
            }

        def ser_disp(d):
            return {
                "direction": d.direction,
                "quality_score": d.quality_score,
                "body_to_range": round(d.body_to_range, 3),
                "atr_multiple": round(d.atr_multiple, 2),
            }

        return AnalysisResult(
            symbol=symbol,
            timeframe=timeframe,
            timestamp_utc=now,
            data_quality=asdict(quality),
            current_price=current_price,
            bias=structure.get("bias", "neutral"),
            dealing_range={
                "high": dealing.high,
                "low": dealing.low,
                "equilibrium": dealing.equilibrium,
                "levels": dealing.levels,
            }
            if dealing
            else None,
            premium_discount=pd_class,
            swings_count=len(swings),
            fvgs=[ser_fvg(f) for f in fvgs[-8:]],
            active_fvgs=[ser_fvg(f) for f in active[:5]],
            liquidity_pools=[ser_pool(p) for p in pools[:12]],
            sweeps=[ser_sweep(s) for s in sweeps[-5:]],
            displacements=[ser_disp(d) for d in displacements[-5:]],
            structure_events=[
                {
                    "type": e.event_type,
                    "direction": e.direction,
                    "price": e.price,
                    "broken_level": e.broken_level,
                }
                for e in bos_events[-5:]
            ],
            setup_status=status,
            notes=notes,
        )

    except Exception as exc:
        logger.exception("Analysis failed for %s %s", symbol, timeframe)
        return AnalysisResult(
            symbol=symbol,
            timeframe=timeframe,
            timestamp_utc=now,
            data_quality={},
            current_price=None,
            bias="unknown",
            dealing_range=None,
            premium_discount=None,
            swings_count=0,
            setup_status="NO_SETUP",
            error=str(exc),
            notes=["Exception during analysis"],
        )


def run_multi_symbol_scan(
    symbols: List[str],
    timeframe: str = "15M",
    provider: Optional[BaseDataProvider] = None,
) -> List[AnalysisResult]:
    provider = provider or get_provider()
    results = []
    for sym in symbols:
        logger.info("Analyzing %s %s", sym, timeframe)
        results.append(analyze_symbol(sym, timeframe, provider=provider))
    return results
