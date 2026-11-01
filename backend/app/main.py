"""
ICT Institutional AI Trading Scanner — FastAPI entry point
"""

from fastapi import FastAPI, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
from dataclasses import asdict
import logging
import os

from .engines.pipeline import analyze_symbol, run_multi_symbol_scan
from .engines.backtest import run_backtest
from .data.provider import get_provider
from .core.auth import require_api_key, api_key_enabled
from .storage.signal_store import save_scan_results, get_recent_signals, get_recent_scans, storage_health
from .scheduler.scanner import (
    start_scheduler, stop_scheduler, pause_scheduler,
    resume_scheduler, get_scheduler_status, trigger_manual_scan,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ict_scanner")

VERSION = "1.0.0-liquidity-nexus"

app = FastAPI(
    title="LIQUIDITY NEXUS",
    description="Decode Liquidity. Follow Smart Money. Signal-only ICT scanner.",
    version=VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
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
    "sessions", "news_filter", "smt", "backtest", "auth",
    "ict_2022", "silver_bullet", "unicorn", "turtle_soup",
    "ote", "judas", "po3", "pipeline",
]


class HealthResponse(BaseModel):
    status: str
    timestamp_utc: str
    version: str
    mode: str = "SIGNAL_ONLY"
    auth_enabled: bool = False


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
        "name": "LIQUIDITY NEXUS",
        "tagline": "Decode Liquidity. Follow Smart Money.",
        "version": VERSION,
        "mode": "SIGNAL_ONLY",
        "philosophy": "NO VALID SETUP = NO TRADE",
        "auth_enabled": api_key_enabled(),
        "docs": "/docs",
        "engines": ENGINES,
    }


@app.on_event("startup")
def startup_scheduler():
    """Start the server-side scanner independently of browser/mobile clients."""
    import os
    if os.getenv("ENABLE_SCHEDULER", "false").lower() in ("1", "true", "yes", "on"):
        interval = int(os.getenv("SCAN_INTERVAL_MINUTES", "20"))
        start_scheduler(interval_minutes=interval, symbols=DEFAULT_SYMBOLS, timeframe="15M")


@app.on_event("shutdown")
def shutdown_scheduler():
    stop_scheduler()


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        version=VERSION,
        auth_enabled=api_key_enabled(),
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
    _: None = Depends(require_api_key),
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
    step: int = Query(20, ge=5, le=100),
    _: None = Depends(require_api_key),
):
    report = run_backtest(symbol.upper(), timeframe=timeframe, limit=limit, step=step)
    return report.to_dict()


@app.post("/api/v1/scan")
def trigger_scan(req: ScanRequest, x_scan_source: str = Header("manual", alias="X-Scan-Source"), x_github_run_id: Optional[str] = Header(None, alias="X-GitHub-Run-Id"), _: None = Depends(require_api_key)):
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

    persistence = save_scan_results(serialized, source=x_scan_source, workflow_run_id=x_github_run_id)
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
        "persistence": persistence,
        "message": "Analysis complete. Only CONFIRMED setups with valid RR are actionable (signal-only).",
    }


@app.get("/api/v1/analyze/{symbol}")
def analyze_one(
    symbol: str,
    timeframe: str = Query("15M"),
    _: None = Depends(require_api_key),
):
    return asdict(analyze_symbol(symbol.upper(), timeframe=timeframe))


@app.get("/api/v1/signals")
def get_signals(status: Optional[str] = None, limit: int = Query(100, ge=1, le=500), _: None = Depends(require_api_key)):
    signals = get_recent_signals(limit=limit, status=status)
    return {"signals": signals, "count": len(signals), "storage": "Vercel Blob (private)" if os.getenv("BLOB_READ_WRITE_TOKEN") else "unconfigured"}


@app.get("/api/v1/scanner/status")
def scanner_status():
    """Expose scheduler-backed status derived from persisted GitHub Actions runs."""
    now = datetime.now(timezone.utc)
    scans = get_recent_scans(limit=50)
    latest = scans[0] if scans else None
    scheduled = next((item for item in scans if item.get("source") == "scheduled"), None)
    last_scheduled = None
    if scheduled and scheduled.get("timestamp_utc"):
        try:
            last_scheduled = datetime.fromisoformat(str(scheduled["timestamp_utc"]).replace("Z", "+00:00"))
            if last_scheduled.tzinfo is None:
                last_scheduled = last_scheduled.replace(tzinfo=timezone.utc)
        except ValueError:
            last_scheduled = None

    # GitHub Actions workflow cron is */20 * * * * (UTC). A recent
    # successful scheduled snapshot is the activation signal, not a browser timer.
    next_minute = ((now.minute // 20) + 1) * 20
    if next_minute >= 60:
        next_run = now.replace(minute=0, second=0, microsecond=0) + __import__("datetime").timedelta(hours=1)
    else:
        next_run = now.replace(minute=next_minute, second=0, microsecond=0)
    age_seconds = (now - last_scheduled).total_seconds() if last_scheduled else None
    storage = storage_health()
    active = bool(storage.get("available") and age_seconds is not None and 0 <= age_seconds <= 2400)
    latest_data = latest.get("data_available") if latest else False
    return {
        "scheduler": "GitHub Actions",
        "cron": "*/20 * * * *",
        "timezone": "UTC",
        "active": active,
        "status": "ACTIVE" if active else "INACTIVE",
        "scanning": False,
        "last_successful_scan_utc": last_scheduled.isoformat() if last_scheduled else None,
        "last_scan_utc": latest.get("timestamp_utc") if latest else None,
        "next_scan_utc": next_run.isoformat(),
        "last_scheduled_workflow_run_id": scheduled.get("workflow_run_id") if scheduled else None,
        "scanned": latest.get("scanned", 0) if latest else 0,
        "confirmed": latest.get("confirmed", 0) if latest else 0,
        "developing": latest.get("developing", 0) if latest else 0,
        "no_setup": latest.get("no_setup", 0) if latest else 0,
        "data_available": bool(latest_data),
        "storage": storage,
        "latest_results": latest.get("results", []) if latest else [],
        "recent_scans": [{k: v for k, v in item.items() if k != "results"} for item in scans],
        "active_reason": "Recent successful scheduled workflow scan and persistent storage are available" if active else "No recent successful scheduled workflow scan; waiting for the next verified run",
    }


@app.get("/api/v1/storage/health")
def persistent_storage_health():
    return storage_health()


@app.get("/api/v1/status")
def system_status():
    return {
        "mode": "SIGNAL_ONLY",
        "version": VERSION,
        "git_commit": os.getenv("VERCEL_GIT_COMMIT_SHA", "unknown"),
        "git_branch": os.getenv("VERCEL_GIT_COMMIT_REF", "unknown"),
        "auth_enabled": api_key_enabled(),
        "data_feed": "authenticated Twelve Data only; TWELVE_DATA_API_KEY required; Yahoo and synthetic trading feeds disabled",
        "scheduler": get_scheduler_status(),
        "engines_ready": ENGINES,
    }


@app.post("/api/v1/scheduler/start")
def scheduler_start(cfg: SchedulerConfig = SchedulerConfig(), _: None = Depends(require_api_key)):
    start_scheduler(interval_minutes=cfg.interval_minutes,
                    symbols=cfg.symbols or DEFAULT_SYMBOLS, timeframe=cfg.timeframe)
    return {"status": "started", **get_scheduler_status()}


@app.post("/api/v1/scheduler/stop")
def scheduler_stop(_: None = Depends(require_api_key)):
    stop_scheduler()
    return {"status": "stopped", **get_scheduler_status()}


@app.post("/api/v1/scheduler/pause")
def scheduler_pause(_: None = Depends(require_api_key)):
    pause_scheduler()
    return {"status": "paused", **get_scheduler_status()}


@app.post("/api/v1/scheduler/resume")
def scheduler_resume(_: None = Depends(require_api_key)):
    resume_scheduler()
    return {"status": "resumed", **get_scheduler_status()}


@app.get("/api/v1/scheduler/status")
def scheduler_status(_: None = Depends(require_api_key)):
    return get_scheduler_status()


@app.post("/api/v1/scheduler/trigger")
def scheduler_trigger(req: ScanRequest = ScanRequest(), _: None = Depends(require_api_key)):
    results = trigger_manual_scan(symbols=req.symbols, timeframe=req.timeframe)
    return {"status": "triggered", "results": results, **get_scheduler_status()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
