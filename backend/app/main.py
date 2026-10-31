"""
ICT Institutional AI Trading Scanner — FastAPI entry point
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ict_scanner")

app = FastAPI(
    title="ICT Institutional AI Trading Scanner",
    description="Signal-only ICT scanner. Selective. NO TRADE is preferred when conditions fail.",
    version="0.1.0-mvp",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str
    timestamp_utc: str
    version: str
    mode: str = "SIGNAL_ONLY"


class ScanRequest(BaseModel):
    symbols: Optional[List[str]] = None
    force: bool = False


@app.get("/")
def root():
    return {
        "name": "ICT Institutional AI Trading Scanner",
        "mode": "SIGNAL_ONLY",
        "philosophy": "NO VALID SETUP = NO TRADE",
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        version="0.1.0-mvp",
    )


@app.get("/api/v1/instruments")
def list_instruments():
    """Supported instruments (user can extend)."""
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
    Trigger a full scan cycle.
    In MVP this returns a stub. Production version runs the full engine stack.
    """
    logger.info("Scan requested: %s", req.symbols or "all")
    return {
        "status": "accepted",
        "message": "Scan queued. Full engine integration pending production data feeds and model completion.",
        "requested_symbols": req.symbols or "all",
        "mode": "SIGNAL_ONLY",
        "note": "NO TRADE is returned when mandatory ICT conditions are not met.",
    }


@app.get("/api/v1/signals")
def get_signals(status: Optional[str] = None):
    """Return current signals. Empty list is a valid and expected state."""
    return {
        "signals": [],
        "count": 0,
        "message": "No active signals. This is the preferred default state of a selective ICT scanner.",
    }


@app.get("/api/v1/status")
def system_status():
    return {
        "scheduler": "not_started_in_mvp",
        "last_scan": None,
        "next_scan": None,
        "data_feed": "historical_only_mvp",
        "mode": "SIGNAL_ONLY",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
