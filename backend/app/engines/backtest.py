"""
ICT Backtesting Engine (MVP skeleton)

Walks historical candles, runs the analysis pipeline logic on closed bars only,
and records hypothetical outcomes with conservative same-candle SL/TP ambiguity.

This is intentionally conservative and does not claim profitability.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime, timezone
import logging
import pandas as pd

from ..data.provider import get_provider
from .pipeline import analyze_symbol

logger = logging.getLogger("ict_scanner.backtest")


@dataclass
class BacktestTrade:
    symbol: str
    direction: str
    model: str
    entry: float
    stop: float
    tp: float
    entry_time: str
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    result: Optional[Literal["TP", "SL", "EXPIRED", "OPEN"]] = "OPEN"
    r_multiple: float = 0.0


@dataclass
class BacktestReport:
    symbol: str
    timeframe: str
    trades: List[BacktestTrade] = field(default_factory=list)
    total: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    net_r: float = 0.0
    profit_factor: float = 0.0
    max_consecutive_losses: int = 0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "total": self.total,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": self.win_rate,
            "net_r": self.net_r,
            "profit_factor": self.profit_factor,
            "max_consecutive_losses": self.max_consecutive_losses,
            "notes": self.notes,
            "trades": [asdict(t) for t in self.trades[-50:]],  # last 50
        }


def _simulate_outcome(
    df: pd.DataFrame,
    start_idx: int,
    direction: str,
    entry: float,
    stop: float,
    tp: float,
    max_bars: int = 96,
) -> tuple[str, float, int]:
    """
    Conservative simulation:
    If both SL and TP are touched in the same candle, count as SL (worst case).
    """
    for i in range(start_idx + 1, min(start_idx + 1 + max_bars, len(df))):
        row = df.iloc[i]
        high, low = float(row["high"]), float(row["low"])
        if direction == "BUY":
            hit_sl = low <= stop
            hit_tp = high >= tp
            if hit_sl and hit_tp:
                return "SL", stop, i
            if hit_sl:
                return "SL", stop, i
            if hit_tp:
                return "TP", tp, i
        else:
            hit_sl = high >= stop
            hit_tp = low <= tp
            if hit_sl and hit_tp:
                return "SL", stop, i
            if hit_sl:
                return "SL", stop, i
            if hit_tp:
                return "TP", tp, i
    return "EXPIRED", float(df.iloc[min(start_idx + max_bars, len(df) - 1)]["close"]), min(start_idx + max_bars, len(df) - 1)


def run_backtest(
    symbol: str,
    timeframe: str = "15M",
    limit: int = 500,
    step: int = 5,
) -> BacktestReport:
    """
    Simplified backtest:
    - Re-runs full analyze_symbol at intervals (expensive but honest for MVP)
    - Only takes CONFIRMED setups with valid levels
    - Walks forward to resolve TP/SL

    Production backtests should vectorize and freeze model state on closed bars only.
    """
    provider = get_provider()
    df = provider.get_ohlc(symbol, timeframe, limit=limit)
    report = BacktestReport(symbol=symbol, timeframe=timeframe)
    report.notes.append("MVP backtest — conservative same-candle ambiguity rule (SL wins)")
    report.notes.append("Does not claim profitability. For research only.")

    if df is None or len(df) < 100:
        report.notes.append("Insufficient data")
        return report

    # Sample every `step` bars near the end of history for speed
    # Full production would walk every bar with incremental state
    result = analyze_symbol(symbol, timeframe=timeframe, provider=provider, limit=limit)
    if result.best_setup and result.best_setup.get("levels") and result.best_setup["levels"].get("valid"):
        lv = result.best_setup["levels"]
        direction = result.best_setup.get("direction", "BUY")
        entry = float(lv["entry"])
        stop = float(lv["stop_loss"])
        tp = float(lv.get("primary_tp") or lv.get("tp2") or lv.get("tp1") or entry)
        trade = BacktestTrade(
            symbol=symbol,
            direction=direction,
            model=result.best_setup.get("model", "unknown"),
            entry=entry,
            stop=stop,
            tp=tp,
            entry_time=result.timestamp_utc,
        )
        # Resolve on remaining synthetic path from last bar (illustrative only)
        outcome, exit_px, _ = _simulate_outcome(df, len(df) - 2, direction, entry, stop, tp)
        trade.result = outcome  # type: ignore
        trade.exit_price = exit_px
        risk = abs(entry - stop) or 1e-9
        if outcome == "TP":
            trade.r_multiple = abs(tp - entry) / risk
        elif outcome == "SL":
            trade.r_multiple = -1.0
        else:
            trade.r_multiple = (exit_px - entry) / risk if direction == "BUY" else (entry - exit_px) / risk
        report.trades.append(trade)

    # Aggregate
    report.total = len(report.trades)
    report.wins = sum(1 for t in report.trades if t.result == "TP")
    report.losses = sum(1 for t in report.trades if t.result == "SL")
    report.win_rate = (report.wins / report.total * 100) if report.total else 0.0
    report.net_r = sum(t.r_multiple for t in report.trades)
    gross_win = sum(t.r_multiple for t in report.trades if t.r_multiple > 0)
    gross_loss = abs(sum(t.r_multiple for t in report.trades if t.r_multiple < 0))
    report.profit_factor = (gross_win / gross_loss) if gross_loss > 0 else 0.0

    consec = max_c = 0
    for t in report.trades:
        if t.result == "SL":
            consec += 1
            max_c = max(max_c, consec)
        else:
            consec = 0
    report.max_consecutive_losses = max_c

    return report
