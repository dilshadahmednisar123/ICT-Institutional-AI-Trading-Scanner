"""
Core Analysis Pipeline

Runs deterministic ICT engines + multiple model state machines + scoring.
Models: ICT 2022, Silver Bullet, Unicorn, Turtle Soup.
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
from .models.silver_bullet import evaluate_silver_bullet, SBState
from .models.unicorn import evaluate_unicorn, UnicornState
from .models.turtle_soup import evaluate_turtle_soup, TSState
from .scoring import score_setup
from .sessions import session_score, is_in_silver_bullet_window, active_session_names

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
    sessions: List[str] = field(default_factory=list)
    in_silver_bullet_window: bool = False
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
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    try:
        df = provider.get_ohlc(symbol, timeframe, limit=limit)
        quality = provider.validate(df, symbol, timeframe)

        if not quality.is_valid or df is None or df.empty:
            return AnalysisResult(
                symbol=symbol,
                timeframe=timeframe,
                timestamp_utc=now_iso,
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
        sessions = active_session_names(now)
        in_sb, sb_label = is_in_silver_bullet_window(now)
        sess_score = session_score(now)

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

        bias = structure.get("bias", "neutral")

        # --- Models ---
        ict2022 = evaluate_ict_2022(
            symbol=symbol, current_price=current_price, htf_bias=bias,
            sweeps=sweeps, displacements=displacements, fvgs=fvgs,
            order_blocks=order_blocks, liquidity_pools=pools,
            dealing_range=dealing, premium_discount=pd_class, atr=atr, min_rr=min_rr,
        )
        silver = evaluate_silver_bullet(
            symbol=symbol, current_price=current_price, htf_bias=bias,
            sweeps=sweeps, displacements=displacements, fvgs=fvgs,
            liquidity_pools=pools, atr=atr, min_rr=min_rr, now=now,
        )
        unicorn = evaluate_unicorn(
            symbol=symbol, current_price=current_price, htf_bias=bias,
            sweeps=sweeps, displacements=displacements, fvgs=fvgs,
            order_blocks=order_blocks, liquidity_pools=pools, atr=atr, min_rr=min_rr,
        )
        turtle = evaluate_turtle_soup(
            symbol=symbol, current_price=current_price, htf_bias=bias,
            sweeps=sweeps, displacements=displacements,
            liquidity_pools=pools, atr=atr, min_rr=min_rr,
        )

        scored: List[Dict[str, Any]] = []
        best = None
        best_score = -1.0

        def consider(d: Dict[str, Any], score: float, active_states: set):
            nonlocal best, best_score
            scored.append(d)
            st = d.get("state", "")
            if score > best_score and st in active_states:
                best_score = score
                best = d

        for s in ict2022:
            bd = score_setup(s, has_mss=bool(bos_events), session_score=sess_score)
            s.score = bd.total
            s.notes.extend(bd.notes)
            d = s.to_dict()
            d["score_breakdown"] = {"total": bd.total, "classification": bd.classification, "components": bd.components}
            consider(d, bd.total, {ModelState.CONFIRMED.value, ModelState.ENTRY_ZONE_READY.value, ModelState.FVG_FORMED.value})

        for s in silver:
            if s.state == SBState.OUTSIDE_WINDOW:
                continue
            d = s.to_dict()
            sc = min(100.0, 55 + sess_score * 5 + (10 if s.state == SBState.CONFIRMED else 0))
            d["score"] = sc
            consider(d, sc, {SBState.CONFIRMED.value, SBState.ENTRY_READY.value, SBState.FVG_READY.value})

        for s in unicorn:
            d = s.to_dict()
            sc = 60.0
            if s.state == UnicornState.CONFIRMED:
                sc = 85.0
            elif s.state == UnicornState.ENTRY_READY:
                sc = 72.0
            elif s.state == UnicornState.FVG_CONFLUENCE:
                sc = 65.0
            d["score"] = sc
            consider(d, sc, {UnicornState.CONFIRMED.value, UnicornState.ENTRY_READY.value, UnicornState.FVG_CONFLUENCE.value})

        for s in turtle:
            d = s.to_dict()
            sc = 50.0
            if s.state == TSState.CONFIRMED:
                sc = 80.0
            elif s.state == TSState.ENTRY_READY:
                sc = 68.0
            elif s.state == TSState.DISPLACEMENT:
                sc = 62.0
            d["score"] = sc
            consider(d, sc, {TSState.CONFIRMED.value, TSState.ENTRY_READY.value, TSState.DISPLACEMENT.value})

        confirmed = (
            [s for s in ict2022 if s.state == ModelState.CONFIRMED]
            + [s for s in silver if s.state == SBState.CONFIRMED]
            + [s for s in unicorn if s.state == UnicornState.CONFIRMED]
            + [s for s in turtle if s.state == TSState.CONFIRMED]
        )
        developing = (
            [s for s in ict2022 if s.state in (ModelState.ENTRY_ZONE_READY, ModelState.FVG_FORMED, ModelState.DISPLACEMENT, ModelState.SWEEP_OCCURRED)]
            + [s for s in silver if s.state in (SBState.ENTRY_READY, SBState.FVG_READY, SBState.DISPLACEMENT, SBState.SWEEP)]
            + [s for s in unicorn if s.state in (UnicornState.ENTRY_READY, UnicornState.FVG_CONFLUENCE, UnicornState.BREAKER_FOUND, UnicornState.DISPLACEMENT)]
            + [s for s in turtle if s.state in (TSState.ENTRY_READY, TSState.DISPLACEMENT, TSState.RECLAIM)]
        )

        notes: List[str] = []
        status: Literal["NO_SETUP", "DEVELOPING", "CONFIRMED", "INVALIDATED"] = "NO_SETUP"
        if confirmed:
            status = "CONFIRMED"
            notes.append(f"{len(confirmed)} CONFIRMED setup(s)")
        elif developing:
            status = "DEVELOPING"
            notes.append(f"{len(developing)} developing setup(s) — not executable")
        else:
            notes.append("No qualifying ICT sequence — NO TRADE")

        if in_sb:
            notes.append(f"Inside Silver Bullet window: {sb_label}")

        def ser_fvg(f):
            return {"direction": f.direction, "upper": f.upper, "lower": f.lower, "midpoint": f.midpoint, "mitigated_pct": f.mitigated_pct}

        def ser_pool(p):
            return {"price": p.price, "side": p.side, "kind": p.kind, "strength": p.strength, "swept": p.swept}

        def ser_ob(o):
            return {"direction": o.direction, "high": o.high, "low": o.low, "midpoint": o.midpoint, "quality": o.quality, "invalidated": o.invalidated, "is_breaker": o.is_breaker}

        return AnalysisResult(
            symbol=symbol,
            timeframe=timeframe,
            timestamp_utc=now_iso,
            data_quality=asdict(quality),
            current_price=current_price,
            bias=bias,
            dealing_range={
                "high": dealing.high, "low": dealing.low, "equilibrium": dealing.equilibrium,
                "levels": {str(k): v for k, v in dealing.levels.items()},
            } if dealing else None,
            premium_discount=pd_class,
            swings_count=len(swings),
            sessions=sessions,
            in_silver_bullet_window=in_sb,
            fvgs=[ser_fvg(f) for f in fvgs[-6:]],
            active_fvgs=[ser_fvg(f) for f in active[:4]],
            liquidity_pools=[ser_pool(p) for p in pools[:10]],
            sweeps=[{"side": s.side, "classification": s.classification, "sweep_price": s.sweep_price, "pool_price": s.pool.price} for s in sweeps[-5:]],
            displacements=[{"direction": d.direction, "quality_score": d.quality_score, "body_to_range": round(d.body_to_range, 3)} for d in displacements[-5:]],
            order_blocks=[ser_ob(o) for o in active_obs[:5]],
            structure_events=[{"type": e.event_type, "direction": e.direction, "price": e.price} for e in bos_events[-5:]],
            model_setups=scored,
            best_setup=best,
            setup_status=status,
            notes=notes,
        )

    except Exception as exc:
        logger.exception("Analysis failed for %s %s", symbol, timeframe)
        return AnalysisResult(
            symbol=symbol, timeframe=timeframe, timestamp_utc=now_iso, data_quality={},
            current_price=None, bias="unknown", dealing_range=None, premium_discount=None,
            swings_count=0, setup_status="NO_SETUP", error=str(exc), notes=["Exception during analysis"],
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
