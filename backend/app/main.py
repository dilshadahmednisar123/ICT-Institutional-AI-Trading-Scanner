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
from .data.provider import get_provider
from .scheduler.scanner import (
    start_scheduler,
    stop_scheduler,
    pause_scheduler,
    resume_scheduler,
    get_scheduler_status,
    trigger_manual_scan,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ict_scanner")

app = FastAPI(
    title="ICT Institutional AI Trading Scanner",
    description="Signal-only ICT scanner. Selective. NO TRADE is preferred when conditions fail.",
    version="0.4.0-sessions-scheduler",
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
        "version": "0.4.0-sessions-scheduler",
        "mode": "SIGNAL_ONLY",
        "philosophy": "NO VALID SETUP = NO TRADE",
        "docs": "/docs",
        "engines": [
            "structure", "fvg", "liquidity", "displacement",
            "premium_discount", "order_blocks", "entry_risk",
            "scoring", "sessions", "ict_2022", "silver_bullet", "pipeline",
        ],
    }


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        version="0.4.0-sessions-scheduler",
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
    return {
        "majors": majors,
        "minors": minors,
        "commodities": metals,
        "total": len(majors) + len(minors) + len(metals),
    }


@app.post("/api/v1/scan")
def trigger_scan(req: ScanRequest):
    symbols = req.symbols or DEFAULT_SYMBOLS
    logger.info("Scan requested for %s @ %s", symbols, req.timeframe)

    provider = get_provider("dukascopy")
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
        "version": "0.4.0-sessions-scheduler",
        "scanned": len(serialized),
        "confirmed": len(confirmed),
        "developing": len(developing),
        "no_setup": len(serialized) - len(confirmed) - len(developing),
        "results": serialized,
        "message": "Analysis complete. Only CONFIRMED setups with valid RR are considered actionable (signal-only).",
    }


@app.get("/api/v1/analyze/{symbol}")
def analyze_one(
    symbol: str,
    timeframe: str = Query("15M"),
):
    result = analyze_symbol(symbol.upper(), timeframe=timeframe)
    return asdict(result)


@app.get("/api/v1/signals")
def get_signals(status: Optional[str] = None):
    return {
        "signals": [],
        "count": 0,
        "message": "No persistent signal store yet. Use /api/v1/scan or scheduler.",
    }


@app.get("/api/v1/status")
def system_status():
    sched = get_scheduler_status()
    return {
        "mode": "SIGNAL_ONLY",
        "version": "0.4.0-sessions-scheduler",
        "data_feed": "dukascopy_historical_placeholder + synthetic_fallback",
        "scheduler": sched,
        "engines_ready": [
            "structure", "fvg", "liquidity", "displacement",
            "premium_discount", "order_blocks", "entry_risk",
            "scoring", "sessions", "ict_2022", "silver_bullet", "pipeline",
        ],
    }


# ---------- Scheduler controls ----------

@app.post("/api/v1/scheduler/start")
def scheduler_start(cfg: SchedulerConfig = SchedulerConfig()):
    start_scheduler(
        interval_minutes=cfg.interval_minutes,
        symbols=cfg.symbols or DEFAULT_SYMBOLS,
        timeframe=cfg.timeframe,
    )
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
