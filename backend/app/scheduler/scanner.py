"""
Persistent Scanner Scheduler

Default: APScheduler BackgroundScheduler (in-process).
Optional Redis job store when REDIS_URL is set (multi-process friendly path).

Default interval: 20 minutes.
"""

from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..engines.pipeline import run_multi_symbol_scan
from ..data.provider import get_provider

logger = logging.getLogger("ict_scanner.scheduler")

DEFAULT_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "XAUUSD",
    "AUDUSD", "USDCAD", "EURJPY", "GBPJPY",
]

_scheduler: Optional[BackgroundScheduler] = None
_last_scan: Optional[datetime] = None
_last_results: List[Dict[str, Any]] = []
_scan_count: int = 0
_paused: bool = False


def _build_scheduler() -> BackgroundScheduler:
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        try:
            from apscheduler.jobstores.redis import RedisJobStore
            jobstores = {"default": RedisJobStore.from_url(redis_url)}
            logger.info("Using Redis job store: %s", redis_url.split("@")[-1])
            return BackgroundScheduler(timezone="UTC", jobstores=jobstores)
        except Exception as exc:
            logger.warning("Redis job store unavailable (%s) — falling back to memory", exc)
    return BackgroundScheduler(timezone="UTC")


def _run_scan_job(symbols: Optional[List[str]] = None, timeframe: str = "15M") -> None:
    global _last_scan, _last_results, _scan_count
    if _paused:
        logger.info("Scheduler paused — skipping scan")
        return

    symbols = symbols or DEFAULT_SYMBOLS
    logger.info("Scheduled scan starting for %s", symbols)
    try:
        provider = get_provider("auto")
        results = run_multi_symbol_scan(symbols, timeframe=timeframe, provider=provider)
        _last_results = [
            {
                "symbol": r.symbol,
                "setup_status": r.setup_status,
                "bias": r.bias,
                "current_price": r.current_price,
                "best_setup": r.best_setup,
                "notes": r.notes,
            }
            for r in results
        ]
        _last_scan = datetime.now(timezone.utc)
        _scan_count += 1
        confirmed = sum(1 for r in results if r.setup_status == "CONFIRMED")
        logger.info("Scan #%s complete — %s symbols, %s confirmed", _scan_count, len(results), confirmed)
    except Exception:
        logger.exception("Scheduled scan failed")


def start_scheduler(
    interval_minutes: int = 20,
    symbols: Optional[List[str]] = None,
    timeframe: str = "15M",
) -> BackgroundScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        logger.warning("Scheduler already running")
        return _scheduler

    _scheduler = _build_scheduler()
    _scheduler.add_job(
        _run_scan_job,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="ict_scan",
        kwargs={"symbols": symbols, "timeframe": timeframe},
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("Scheduler started — every %s minutes", interval_minutes)
    _run_scan_job(symbols=symbols, timeframe=timeframe)
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")


def pause_scheduler() -> None:
    global _paused
    _paused = True
    logger.info("Scheduler paused")


def resume_scheduler() -> None:
    global _paused
    _paused = False
    logger.info("Scheduler resumed")


def get_scheduler_status() -> Dict[str, Any]:
    next_run = None
    running = False
    jobstore = "memory"
    if os.getenv("REDIS_URL", "").strip():
        jobstore = "redis"
    if _scheduler and _scheduler.running:
        running = True
        job = _scheduler.get_job("ict_scan")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

    return {
        "running": running,
        "paused": _paused,
        "jobstore": jobstore,
        "scan_count": _scan_count,
        "last_scan_utc": _last_scan.isoformat() if _last_scan else None,
        "next_scan_utc": next_run,
        "last_results_summary": _last_results,
    }


def trigger_manual_scan(
    symbols: Optional[List[str]] = None,
    timeframe: str = "15M",
) -> List[Dict[str, Any]]:
    _run_scan_job(symbols=symbols, timeframe=timeframe)
    return _last_results
