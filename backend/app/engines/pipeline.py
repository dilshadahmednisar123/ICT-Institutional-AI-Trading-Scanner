"""
Core Analysis Pipeline — multi-model ICT scanner
Models: 2022, Silver Bullet, Unicorn, Turtle Soup, OTE, Judas, PO3 + SMT
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
from .models.ote import evaluate_ote, OTEState
from .models.judas import evaluate_judas, JudasState
from .models.po3 import evaluate_po3, PO3State
from .scoring import score_setup
from .sessions import session_score, is_in_silver_bullet_window, active_session_names
from .news_filter import default_news_filter
from .smt import detect_smt, DEFAULT_CORRELATIONS

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
    news_risk: str = "Unknown"
    smt: Optional[Dict[str, Any]] = None
    chart_overlays: Optional[Dict[str, Any]] = None
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


def _ser_fvg(f):
    return {"direction": f.direction, "upper": f.upper, "lower": f.lower, "midpoint": f.midpoint, "mitigated_pct": f.mitigated_pct}


def _ser_pool(p):
    return {"price": p.price, "side": p.side, "kind": p.kind, "strength": p.strength, "swept": p.swept}


def _ser_ob(o):
    return {"direction": o.direction, "high": o.high, "low": o.low, "midpoint": o.midpoint, "quality": o.quality, "invalidated": o.invalidated, "is_breaker": o.is_breaker}


def analyze_symbol(
    symbol: str,
    timeframe: str = "15M",
    provider: Optional[BaseDataProvider] = None,
    limit: int = 400,
    min_rr: float = 2.0,
) -> AnalysisResult:
    provider = provider or get_provider("auto")
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    try:
        df = provider.get_ohlc(symbol, timeframe, limit=limit)
        quality = provider.validate(df, symbol, timeframe)

        if not quality.is_valid or df is None or df.empty:
            return AnalysisResult(
                symbol=symbol, timeframe=timeframe, timestamp_utc=now_iso,
                data_quality=asdict(quality), current_price=None, bias="unknown",
                dealing_range=None, premium_discount=None, swings_count=0,
                setup_status="NO_SETUP", notes=["DATA UNAVAILABLE or invalid"], error=quality.message,
            )
        if quality.stale:
            return AnalysisResult(
                symbol=symbol, timeframe=timeframe, timestamp_utc=now_iso,
                data_quality=asdict(quality), current_price=float(df.iloc[-1]["close"]),
                bias="unknown", dealing_range=None, premium_discount=None, swings_count=0,
                setup_status="NO_SETUP",
                notes=["DATA STALE — no trade signals are generated from stale candles"],
                error="Market data is stale; wait for a fresh provider update.",
            )

        current_price = float(df.iloc[-1]["close"])
        sessions = active_session_names(now)
        in_sb, sb_label = is_in_silver_bullet_window(now)
        sess_score = session_score(now)
        news = default_news_filter.evaluate(symbol, now)

        # SMT vs correlated pair when available
        corr_sym = DEFAULT_CORRELATIONS.get(symbol.upper())
        df_corr = None
        if corr_sym:
            try:
                df_corr = provider.get_ohlc(corr_sym, timeframe, limit=limit)
            except Exception:
                df_corr = None
        smt = detect_smt(symbol, df, df_corr, corr_sym)

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

        m2022 = evaluate_ict_2022(symbol, current_price, bias, sweeps, displacements, fvgs, order_blocks, pools, dealing, pd_class, atr, min_rr)
        msb = evaluate_silver_bullet(symbol, current_price, bias, sweeps, displacements, fvgs, pools, atr, min_rr, now)
        muni = evaluate_unicorn(symbol, current_price, bias, sweeps, displacements, fvgs, order_blocks, pools, atr, min_rr)
        mts = evaluate_turtle_soup(symbol, current_price, bias, sweeps, displacements, pools, atr, min_rr)
        mote = evaluate_ote(symbol, current_price, bias, dealing, sweeps, displacements, fvgs, pools, atr, min_rr)
        mjud = evaluate_judas(symbol, current_price, bias, sweeps, displacements, pools, atr, min_rr, now)
        mpo3 = evaluate_po3(symbol, current_price, bias, df, sweeps, displacements, pools, atr, min_rr)

        scored: List[Dict[str, Any]] = []
        best = None
        best_score = -1.0
        smt_bonus = smt.score if smt.available and smt.divergence else 0.0

        def consider(d: Dict[str, Any], score: float, ok_states: set):
            nonlocal best, best_score
            score = min(100.0, score + smt_bonus * 0.8)
            d["score"] = round(score, 1)
            if news.blocking and "CONFIRMED" in str(d.get("state", "")).upper():
                d["notes"] = (d.get("notes") or []) + [news.message]
                d["setup_status"] = "DEVELOPING"
            scored.append(d)
            st = d.get("state", "")
            if score > best_score and st in ok_states:
                best_score = score
                best = d

        for s in m2022:
            bd = score_setup(s, has_mss=bool(bos_events), session_score=sess_score, smt_score=smt_bonus)
            s.score = bd.total
            s.notes.extend(bd.notes)
            d = s.to_dict()
            d["score_breakdown"] = {"total": bd.total, "classification": bd.classification}
            consider(d, bd.total, {ModelState.CONFIRMED.value, ModelState.ENTRY_ZONE_READY.value, ModelState.FVG_FORMED.value})

        for s in msb:
            if s.state == SBState.OUTSIDE_WINDOW:
                continue
            d = s.to_dict()
            sc = min(100.0, 55 + sess_score * 5 + (15 if s.state == SBState.CONFIRMED else 0))
            consider(d, sc, {SBState.CONFIRMED.value, SBState.ENTRY_READY.value, SBState.FVG_READY.value})

        for s in muni:
            d = s.to_dict()
            sc = float({UnicornState.CONFIRMED: 88, UnicornState.ENTRY_READY: 74, UnicornState.FVG_CONFLUENCE: 66}.get(s.state, 45))
            consider(d, sc, {UnicornState.CONFIRMED.value, UnicornState.ENTRY_READY.value, UnicornState.FVG_CONFLUENCE.value})

        for s in mts:
            d = s.to_dict()
            sc = float({TSState.CONFIRMED: 82, TSState.ENTRY_READY: 70, TSState.DISPLACEMENT: 63}.get(s.state, 40))
            consider(d, sc, {TSState.CONFIRMED.value, TSState.ENTRY_READY.value, TSState.DISPLACEMENT.value})

        for s in mote:
            d = s.to_dict()
            sc = float({OTEState.CONFIRMED: 84, OTEState.IN_OTE_ZONE: 68, OTEState.RANGE_OK: 40}.get(s.state, 30))
            consider(d, sc, {OTEState.CONFIRMED.value, OTEState.IN_OTE_ZONE.value})

        for s in mjud:
            d = s.to_dict()
            sc = float({JudasState.CONFIRMED: 86, JudasState.REVERSAL: 72, JudasState.FALSE_MOVE: 55}.get(s.state, 35))
            if s.session and s.session != "off_session":
                sc += 5
            consider(d, sc, {JudasState.CONFIRMED.value, JudasState.REVERSAL.value})

        for s in mpo3:
            d = s.to_dict()
            sc = float({PO3State.CONFIRMED: 87, PO3State.DISTRIBUTION: 73, PO3State.MANIPULATION: 60, PO3State.ACCUMULATION: 40}.get(s.state, 30))
            consider(d, sc, {PO3State.CONFIRMED.value, PO3State.DISTRIBUTION.value, PO3State.MANIPULATION.value})

        notes: List[str] = []
        status: Literal["NO_SETUP", "DEVELOPING", "CONFIRMED", "INVALIDATED"] = "NO_SETUP"
        if any(d.get("state") == "CONFIRMED" or d.get("setup_status") == "CONFIRMED" for d in scored):
            if news.blocking:
                status = "DEVELOPING"
                notes.append(news.message)
            else:
                status = "CONFIRMED"
                notes.append("CONFIRMED setup(s) present")
        elif any(d.get("setup_status") == "DEVELOPING" or d.get("state") not in ("IDLE", "OUTSIDE_WINDOW", "INVALIDATED", "", "RANGE_OK", "ACCUMULATION") for d in scored):
            status = "DEVELOPING"
            notes.append("Developing setup(s) — not executable")
        else:
            notes.append("No qualifying ICT sequence — NO TRADE")

        if in_sb:
            notes.append(f"Inside Silver Bullet window: {sb_label}")
        if not news.available:
            notes.append(news.message)
        if smt.available and smt.divergence:
            notes.append(f"SMT {smt.divergence}: {smt.detail}")
        elif not smt.available:
            notes.append(smt.detail)

        # Chart overlays for frontend
        overlays: Dict[str, Any] = {
            "fvgs": [_ser_fvg(f) for f in active[:3]],
            "order_blocks": [_ser_ob(o) for o in active_obs[:3]],
            "liquidity": [_ser_pool(p) for p in pools[:6]],
            "dealing_range": {
                "high": dealing.high, "low": dealing.low, "eq": dealing.equilibrium,
            } if dealing else None,
        }
        if best and best.get("levels"):
            lv = best["levels"]
            overlays["trade"] = {
                "entry": lv.get("entry"),
                "stop": lv.get("stop_loss"),
                "tp1": lv.get("tp1"),
                "tp2": lv.get("tp2"),
                "direction": best.get("direction"),
            }

        return AnalysisResult(
            symbol=symbol, timeframe=timeframe, timestamp_utc=now_iso,
            data_quality=asdict(quality), current_price=current_price, bias=bias,
            dealing_range={
                "high": dealing.high, "low": dealing.low, "equilibrium": dealing.equilibrium,
                "levels": {str(k): v for k, v in dealing.levels.items()},
            } if dealing else None,
            premium_discount=pd_class, swings_count=len(swings),
            sessions=sessions, in_silver_bullet_window=in_sb, news_risk=news.risk,
            smt=smt.to_dict(), chart_overlays=overlays,
            fvgs=[_ser_fvg(f) for f in fvgs[-6:]],
            active_fvgs=[_ser_fvg(f) for f in active[:4]],
            liquidity_pools=[_ser_pool(p) for p in pools[:10]],
            sweeps=[{"side": s.side, "classification": s.classification, "sweep_price": s.sweep_price, "pool_price": s.pool.price} for s in sweeps[-5:]],
            displacements=[{"direction": d.direction, "quality_score": d.quality_score} for d in displacements[-5:]],
            order_blocks=[_ser_ob(o) for o in active_obs[:5]],
            structure_events=[{"type": e.event_type, "direction": e.direction, "price": e.price} for e in bos_events[-5:]],
            model_setups=scored, best_setup=best, setup_status=status, notes=notes,
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
    provider = provider or get_provider("auto")
    return [analyze_symbol(sym, timeframe, provider=provider) for sym in symbols]
