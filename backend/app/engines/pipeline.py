"""
Core Analysis Pipeline

Runs the deterministic ICT engines in sequence and produces a structured result
including ICT 2022 model evaluation and confluence scoring.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Literal
import logging

from ..data.provider import BaseDataProvider, get_provider
from .structure import find_swing_points, classify_structure, detect_bos_choch
from .fvg import detect_fvgs, get_active_fvgs
from .liquidity import build_liquidity_map, detect_sweeps
from .displacement import detect_displacement, compute_atr
from .premium_discount import build_dealing_range
from .order_blocks import detect_order_blocks, get_active_order_blocks
from .models.ict_2022 import evaluate_ict_2022, ModelState
from .scoring import score_setup

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
    order_blocks: List[Dict[str, Any]] = field(default_factory=list)
    structure_events: List[Dict[str, Any]] = field(default_factory=list)
    model_setups: List[Dict[str, Any]] = field(default_factory=list)
    best_setup: Optional[Dict[str, Any]] = None
    setup_status: Literal["NO_SETUP", "DEVELOPING", "CONFIRMED", "INVALIDATED"] = "NO_SETUP"
    notes: List[str] = field(default_factory=list)
    error: Optional[str] = None


def analyze_symbol(
    symbol: str,
    timeframe: str = "15M",
    provider: Optional[BaseDataProvider] = None,
    limit: int = 400,
    min_rr: float = 2.0,
) -> AnalysisResult:
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

        # --- Core engines ---
        swings = find_swing_points(df, left=3, right=3, strength="short")
        structure = classify_structure(swings)
        bos_events = detect_bos_choch(df, swings, timeframe=timeframe)

        dealing = build_dealing_range(swings)
        pd_class = dealing.classify(current_price) if dealing else None

        fvgs = detect_fvgs(df, timeframe=timeframe)
        active = get_active_fvgs(fvgs, current_price)

        pools = build_liquidity_map(df, swings, timeframe=timeframe)
        sweeps = detect_sweeps(df, pools)

        displacements = detect_displacement(df)
        atr_series = compute_atr(df)
        atr = float(atr_series.iloc[-1]) if len(atr_series) else None

        order_blocks = detect_order_blocks(df, displacements=displacements, timeframe=timeframe)
        active_obs = get_active_order_blocks(order_blocks, current_price)

        # --- ICT 2022 Model ---
        model_setups = evaluate_ict_2022(
            symbol=symbol,
            current_price=current_price,
            htf_bias=structure.get("bias", "neutral"),
            sweeps=sweeps,
            displacements=displacements,
            fvgs=fvgs,
            order_blocks=order_blocks,
            liquidity_pools=pools,
            dealing_range=dealing,
            premium_discount=pd_class,
            atr=atr,
            min_rr=min_rr,
        )

        # Score each setup
        scored_setups = []
        best = None
        best_score = -1.0

        for s in model_setups:
            breakdown = score_setup(s, has_mss=bool(bos_events))
            s.score = breakdown.total
            s.notes.extend(breakdown.notes)
            d = s.to_dict()
            d["score_breakdown"] = {
                "total": breakdown.total,
                "classification": breakdown.classification,
                "components": breakdown.components,
            }
            scored_setups.append(d)
            if breakdown.total > best_score and s.state != ModelState.IDLE:
                best_score = breakdown.total
                best = d

        # Determine overall status
        status: Literal["NO_SETUP", "DEVELOPING", "CONFIRMED", "INVALIDATED"] = "NO_SETUP"
        notes: List[str] = []

        confirmed = [s for s in model_setups if s.state == ModelState.CONFIRMED]
        developing = [
            s
            for s in model_setups
            if s.state
            in (
                ModelState.ENTRY_ZONE_READY,
                ModelState.FVG_FORMED,
                ModelState.DISPLACEMENT,
                ModelState.SWEEP_OCCURRED,
            )
        ]

        if confirmed:
            status = "CONFIRMED"
            notes.append(f"{len(confirmed)} CONFIRMED ICT 2022 setup(s)")
        elif developing:
            status = "DEVELOPING"
            notes.append(f"{len(developing)} developing setup(s) — not yet executable")
        else:
            notes.append("No qualifying ICT 2022 sequence — NO TRADE")

        def ser_fvg(f):
            return {
                "direction": f.direction,
                "upper": f.upper,
                "lower": f.lower,
                "midpoint": f.midpoint,
                "width": f.width,
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

        def ser_ob(o):
            return {
                "direction": o.direction,
                "high": o.high,
                "low": o.low,
                "midpoint": o.midpoint,
                "quality": o.quality,
                "invalidated": o.invalidated,
                "is_breaker": o.is_breaker,
                "mitigation_pct": o.mitigation_pct,
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
                "levels": {str(k): v for k, v in dealing.levels.items()},
            }
            if dealing
            else None,
            premium_discount=pd_class,
            swings_count=len(swings),
            fvgs=[ser_fvg(f) for f in fvgs[-6:]],
            active_fvgs=[ser_fvg(f) for f in active[:4]],
            liquidity_pools=[ser_pool(p) for p in pools[:10]],
            sweeps=[
                {
                    "side": s.side,
                    "classification": s.classification,
                    "sweep_price": s.sweep_price,
                    "pool_price": s.pool.price,
                    "pool_kind": s.pool.kind,
                }
                for s in sweeps[-5:]
            ],
            displacements=[
                {
                    "direction": d.direction,
                    "quality_score": d.quality_score,
                    "body_to_range": round(d.body_to_range, 3),
                    "atr_multiple": round(d.atr_multiple, 2),
                }
                for d in displacements[-5:]
            ],
            order_blocks=[ser_ob(o) for o in active_obs[:5]],
            structure_events=[
                {
                    "type": e.event_type,
                    "direction": e.direction,
                    "price": e.price,
                    "broken_level": e.broken_level,
                }
                for e in bos_events[-5:]
            ],
            model_setups=scored_setups,
            best_setup=best,
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
