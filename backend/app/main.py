"""
ICT Institutional AI Trading Scanner — FastAPI entry point
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
from dataclasses import asdict
import logging

from .engines.pipeline import analyze_symbol, run_multi_symbol_scan
from .data.provider import get_provider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ict_scanner")

app = FastAPI(
    title="ICT Institutional AI Trading Scanner",
    description="Signal-only ICT scanner. Selective. NO TRADE is preferred when conditions fail.",
    version="0.2.0-core-engines",
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


@app.get("/")
def root():
    return {
        "name": "ICT Institutional AI Trading Scanner",
        "version": "0.2.0-core-engines",
        "mode": "SIGNAL_ONLY",
        "philosophy": "NO VALID SETUP = NO TRADE",
        "docs": "/docs",
        "engines": [
            "structure", "fvg", "liquidity", "displacement",
            "premium_discount", "pipeline",
        ],
    }


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        version="0.2.0-core-engines",
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
    """
    Run the full deterministic ICT analysis pipeline on the requested symbols.
    Returns structured results. CONFIRMED signals are extremely selective.
    """
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
            "setup_status": r.setup_status,
            "swings_count": r.swings_count,
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
        "scanned": len(serialized),
        "confirmed": len(confirmed),
        "developing": len(developing),
        "no_setup": len(serialized) - len(confirmed) - len(developing),
        "results": serialized,
        "message": "Analysis complete. CONFIRMED setups require full model sequence (still being expanded).",
    }


@app.get("/api/v1/analyze/{symbol}")
def analyze_one(
    symbol: str,
    timeframe: str = Query("15M", description="Timeframe e.g. 5M, 15M, 1H, 4H"),
):
    """Deep analysis of a single instrument."""
    result = analyze_symbol(symbol.upper(), timeframe=timeframe)
    return asdict(result)


@app.get("/api/v1/signals")
def get_signals(status: Optional[str] = None):
    """
    Return current signals.
    Empty list is a valid and expected state for a selective ICT scanner.
    """
    return {
        "signals": [],
        "count": 0,
        "message": "No active signals stored yet. Run /api/v1/scan to generate analysis.",
    }


@app.get("/api/v1/status")
def system_status():
    return {
        "scheduler": "manual_only_in_current_version",
        "last_scan": None,
        "next_scan": None,
        "data_feed": "dukascopy_historical_placeholder + synthetic_fallback",
        "mode": "SIGNAL_ONLY",
        "version": "0.2.0-core-engines",
        "engines_ready": [
            "structure", "fvg", "liquidity", "displacement",
            "premium_discount", "pipeline",
        ],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
