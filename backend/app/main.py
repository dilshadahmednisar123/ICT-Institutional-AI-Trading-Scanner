"""
ICT Institutional AI Trading Scanner — FastAPI entry point
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
from dataclasses import asdict
import logging

from .engines.pipeline import analyze_symbol, run_multi_symbol_scan
from .engines.backtest import run_backtest
from .data.provider import get_provider
from .scheduler.scanner import (
    start_scheduler, stop_scheduler, pause_scheduler,
    resume_scheduler, get_scheduler_status, trigger_manual_scan,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ict_scanner")

VERSION = "0.8.0-live-overlays"

app = FastAPI(
    title="ICT Institutional AI Trading Scanner",
    description="Signal-only ICT scanner. Selective. NO TRADE is preferred when conditions fail.",
    version=VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "XAUUSD",
    "AUDUSD", "USDCAD", "EURJPY", "GBPJPY",
]

ENGINES = [
    "structure", "fvg", "liquidity", "displacement",
    "premium_discount", "order_blocks", "entry_risk", "scoring",
    "sessions", "news_filter", "smt", "backtest",
    "ict_2022", "silver_bullet", "unicorn", "turtle_soup",
    "ote", "judas", "po3", "pipeline",
]


class HealthResponse(BaseModel):
    status: str
    timestamp_utc: str
    version: str
    mode: str = "SIGNAL_ONLY"


class ScanRequest(BaseModel):
    symbols: Optional[List[str]] = None
    timeframe: str = "15M"
    force: bool = False


class SchedulerConfig(BaseModel):
    interval_minutes: int = 20
    symbols: Optional[List[str]] = None
    timeframe: str = "15M"


@app.get("/")
def root():
    return {
        "name": "ICT Institutional AI Trading Scanner",
        "version": VERSION,
        "mode": "SIGNAL_ONLY",
        "philosophy": "NO VALID SETUP = NO TRADE",
        "docs": "/docs",
        "engines": ENGINES,
    }


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        version=VERSION,
    )


@app.get("/api/v1/instruments")
def list_instruments():
    majors = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"]
    minors = [
        "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
        "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD",
        "AUDJPY", "AUDNZD", "AUDCAD", "AUDCHF",
        "NZDJPY", "NZDCAD", "NZDCHF", "CADJPY", "CADCHF", "CHFJPY",
    ]
    metals = ["XAUUSD", "XAGUSD"]
    return {"majors": majors, "minors": minors, "commodities": metals,
            "total": len(majors) + len(minors) + len(metals)}


@app.get("/api/v1/ohlc/{symbol}")
def get_ohlc(
    symbol: str,
    timeframe: str = Query("15M"),
    limit: int = Query(200, ge=10, le=2000),
):
    provider = get_provider("auto")
    df = provider.get_ohlc(symbol.upper(), timeframe, limit=limit)
    quality = provider.validate(df, symbol.upper(), timeframe)
    if not quality.is_valid or df is None or df.empty:
        return {"symbol": symbol, "timeframe": timeframe, "candles": [], "quality": asdict(quality)}

    import pandas as pd
    candles = []
    for _, row in df.iterrows():
        ts = row["timestamp"]
        t = int(pd.Timestamp(ts).timestamp())
        candles.append({
            "time": t,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        })
    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "candles": candles,
        "quality": asdict(quality),
        "provider": quality.provider,
    }


@app.get("/api/v1/backtest/{symbol}")
def backtest_symbol(
    symbol: str,
    timeframe: str = Query("15M"),
    limit: int = Query(400, ge=100, le=2000),
):
    report = run_backtest(symbol.upper(), timeframe=timeframe, limit=limit)
    return report.to_dict()


@app.post("/api/v1/scan")
def trigger_scan(req: ScanRequest):
    symbols = req.symbols or DEFAULT_SYMBOLS
    logger.info("Scan requested for %s @ %s", symbols, req.timeframe)
    provider = get_provider("auto")
    results = run_multi_symbol_scan(symbols, timeframe=req.timeframe, provider=provider)

    serialized = []
    for r in results:
        serialized.append({
            "symbol": r.symbol,
            "timeframe": r.timeframe,
            "timestamp_utc": r.timestamp_utc,
            "current_price": r.current_price,
            "bias": r.bias,
            "premium_discount": r.premium_discount,
            "sessions": r.sessions,
            "in_silver_bullet_window": r.in_silver_bullet_window,
            "news_risk": getattr(r, "news_risk", "Unknown"),
            "smt": getattr(r, "smt", None),
            "chart_overlays": getattr(r, "chart_overlays", None),
            "setup_status": r.setup_status,
            "best_setup": r.best_setup,
            "model_setups": r.model_setups,
            "order_blocks": r.order_blocks,
            "active_fvgs": r.active_fvgs,
            "sweeps": r.sweeps,
            "displacements": r.displacements,
            "liquidity_pools": r.liquidity_pools[:6],
            "dealing_range": r.dealing_range,
            "notes": r.notes,
            "data_quality": r.data_quality,
            "error": r.error,
        })

    confirmed = [s for s in serialized if s["setup_status"] == "CONFIRMED"]
    developing = [s for s in serialized if s["setup_status"] == "DEVELOPING"]

    return {
        "status": "completed",
        "mode": "SIGNAL_ONLY",
        "version": VERSION,
        "scanned": len(serialized),
        "confirmed": len(confirmed),
        "developing": len(developing),
        "no_setup": len(serialized) - len(confirmed) - len(developing),
        "results": serialized,
        "message": "Analysis complete. Only CONFIRMED setups with valid RR are actionable (signal-only).",
    }


@app.get("/api/v1/analyze/{symbol}")
def analyze_one(symbol: str, timeframe: str = Query("15M")):
    return asdict(analyze_symbol(symbol.upper(), timeframe=timeframe))


@app.get("/api/v1/signals")
def get_signals(status: Optional[str] = None):
    return {"signals": [], "count": 0, "message": "No persistent signal store yet."}


@app.get("/api/v1/status")
def system_status():
    return {
        "mode": "SIGNAL_ONLY",
        "version": VERSION,
        "data_feed": "auto (Twelve Data if TWELVE_DATA_API_KEY else Dukascopy/synthetic)",
        "scheduler": get_scheduler_status(),
        "engines_ready": ENGINES,
    }


@app.post("/api/v1/scheduler/start")
def scheduler_start(cfg: SchedulerConfig = SchedulerConfig()):
    start_scheduler(interval_minutes=cfg.interval_minutes,
                    symbols=cfg.symbols or DEFAULT_SYMBOLS, timeframe=cfg.timeframe)
    return {"status": "started", **get_scheduler_status()}


@app.post("/api/v1/scheduler/stop")
def scheduler_stop():
    stop_scheduler()
    return {"status": "stopped", **get_scheduler_status()}


@app.post("/api/v1/scheduler/pause")
def scheduler_pause():
    pause_scheduler()
    return {"status": "paused", **get_scheduler_status()}


@app.post("/api/v1/scheduler/resume")
def scheduler_resume():
    resume_scheduler()
    return {"status": "resumed", **get_scheduler_status()}


@app.get("/api/v1/scheduler/status")
def scheduler_status():
    return get_scheduler_status()


@app.post("/api/v1/scheduler/trigger")
def scheduler_trigger(req: ScanRequest = ScanRequest()):
    results = trigger_manual_scan(symbols=req.symbols, timeframe=req.timeframe)
    return {"status": "triggered", "results": results, **get_scheduler_status()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
