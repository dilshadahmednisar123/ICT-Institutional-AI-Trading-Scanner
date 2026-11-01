"""
ICT Backtesting Engine

Walk-forward style MVP:
- Uses only closed historical bars (no lookahead in outcome simulation)
- Conservative same-candle SL/TP ambiguity → SL wins
- Samples analysis windows along history for research (not a claim of edge)

Does not claim profitability.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Literal
import logging
import pandas as pd

from ..data.provider import get_provider, only_closed_candles, TF_MINUTES
from .structure import find_swing_points, classify_structure, detect_bos_choch
from .fvg import detect_fvgs, get_active_fvgs
from .liquidity import build_liquidity_map, detect_sweeps
from .displacement import detect_displacement, compute_atr
from .premium_discount import build_dealing_range
from .order_blocks import detect_order_blocks
from .models.ict_2022 import evaluate_ict_2022, ModelState
from .entry_risk import build_trade_levels, choose_entry_from_fvg

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
    bar_index: int = 0


@dataclass
class BacktestReport:
    symbol: str
    timeframe: str
    trades: List[BacktestTrade] = field(default_factory=list)
    total: int = 0
    wins: int = 0
    losses: int = 0
    expired: int = 0
    win_rate: float = 0.0
    net_r: float = 0.0
    avg_r: float = 0.0
    profit_factor: float = 0.0
    max_consecutive_losses: int = 0
    max_drawdown_r: float = 0.0
    gaps_detected: int = 0
    session_breaks: int = 0
    missing_candles: int = 0
    duplicate_candles: int = 0
    data_provider: str = "unavailable"
    bars_used: int = 0
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "sampling_step_bars": self.sampling_step_bars,
            "total": self.total,
            "wins": self.wins,
            "losses": self.losses,
            "expired": self.expired,
            "win_rate": round(self.win_rate, 2),
            "net_r": round(self.net_r, 3),
            "avg_r": round(self.avg_r, 3),
            "profit_factor": round(self.profit_factor, 3),
            "max_consecutive_losses": self.max_consecutive_losses,
            "max_drawdown_r": round(self.max_drawdown_r, 3),
            "gaps_detected": self.gaps_detected,
            "session_breaks": self.session_breaks,
            "missing_candles": self.missing_candles,
            "duplicate_candles": self.duplicate_candles,
            "data_provider": self.data_provider,
            "bars_used": self.bars_used,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "notes": self.notes,
            "trades": [asdict(t) for t in self.trades[-100:]],
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
    last = min(start_idx + max_bars, len(df) - 1)
    return "EXPIRED", float(df.iloc[last]["close"]), last


def _window_setup(
    symbol: str,
    window: pd.DataFrame,
    min_rr: float = 0.0,
    timeframe: str = "15M",
) -> Optional[BacktestTrade]:
    """Run lightweight ICT 2022 path on a closed window; return trade if CONFIRMED-like."""
    if len(window) < 80:
        return None
    window = window.reset_index(drop=True)

    current_price = float(window.iloc[-1]["close"])
    swings = find_swing_points(window, left=3, right=3)
    structure = classify_structure(swings)
    bias = structure.get("bias", "neutral")
    structure_events = detect_bos_choch(window, swings, timeframe=timeframe)
    dealing = build_dealing_range(swings)
    pd_class = dealing.classify(current_price) if dealing else None
    fvgs = detect_fvgs(window, timeframe=timeframe)
    pools = build_liquidity_map(window, swings, timeframe=timeframe)
    sweeps = detect_sweeps(window, pools)
    displacements = detect_displacement(window)
    atr_series = compute_atr(window)
    atr = float(atr_series.iloc[-1]) if len(atr_series) else None
    order_blocks = detect_order_blocks(window, displacements=displacements, timeframe=timeframe)

    setups = evaluate_ict_2022(
        symbol=symbol,
        current_price=current_price,
        htf_bias=bias,
        sweeps=sweeps,
        displacements=displacements,
        fvgs=fvgs,
        order_blocks=order_blocks,
        liquidity_pools=pools,
        dealing_range=dealing,
        premium_discount=pd_class,
        atr=atr,
        min_rr=min_rr,
        structure_events=structure_events,
        current_bar_high=float(window.iloc[-1]["high"]),
        current_bar_low=float(window.iloc[-1]["low"]),
    )

    for s in setups:
        if s.state == ModelState.CONFIRMED and s.levels and s.levels.valid:
            ts = window.iloc[-1]["timestamp"]
            return BacktestTrade(
                symbol=symbol,
                direction=s.direction,
                model="ICT_2022_Mentorship",
                entry=s.levels.entry_price,
                stop=s.levels.stop_loss,
                tp=float(s.levels.primary_tp or s.levels.take_profit_1 or s.levels.entry_price),
                entry_time=str(ts),
                bar_index=len(window) - 1,
            )
    return None


def run_backtest(
    symbol: str,
    timeframe: str = "15M",
    limit: int = 500,
    step: int = 1,
    window_size: int = 200,
    min_rr: float = 0.0,
    historical_data: Optional[pd.DataFrame] = None,
    historical_provider: str = "external_historical_dataset",
) -> BacktestReport:
    if historical_data is None:
        provider = get_provider("auto")
        df = provider.get_ohlc(symbol, timeframe, limit=limit)
        default_provider = provider.__class__.__name__
    else:
        df = historical_data.copy()
        default_provider = historical_provider
    report = BacktestReport(symbol=symbol, timeframe=timeframe, sampling_step_bars=step)
    if df is not None:
        report.data_provider = str(df.attrs.get("provider", default_provider))
        if not df.empty:
            required = {"timestamp", "open", "high", "low", "close"}
            if not required.issubset(df.columns):
                report.notes.append(f"Historical dataset rejected: missing columns {sorted(required - set(df.columns))}")
                return report
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
            for column in ("open", "high", "low", "close"):
                df[column] = pd.to_numeric(df[column], errors="coerce")
            if df["timestamp"].isna().any() or df[["open", "high", "low", "close"]].isna().any().any():
                report.notes.append("Historical dataset rejected: invalid timestamps or non-numeric OHLC values")
                return report
            if not df["timestamp"].is_monotonic_increasing:
                df = df.sort_values("timestamp").reset_index(drop=True)
                report.notes.append("Historical timestamps were sorted ascending before analysis")
            report.duplicate_candles = int(df["timestamp"].duplicated(keep="last").sum())
            if report.duplicate_candles:
                report.notes.append(f"Historical dataset rejected: {report.duplicate_candles} duplicate timestamps")
                return report
            invalid = (
                (df["high"] < df[["open", "close", "low"]].max(axis=1)) |
                (df["low"] > df[["open", "close", "high"]].min(axis=1)) |
                (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
            )
            if invalid.any():
                report.notes.append(f"Historical dataset rejected: {int(invalid.sum())} invalid OHLC candles")
                return report
            minutes = TF_MINUTES.get(timeframe.upper(), 15)
            if timeframe.upper() == "1D":
                aligned = df["timestamp"].dt.floor("1D")
            elif timeframe.upper() in TF_MINUTES:
                aligned = df["timestamp"].dt.floor(f"{minutes}min")
            else:
                aligned = df["timestamp"]
            misaligned = int((df["timestamp"] != aligned).sum())
            if misaligned:
                report.notes.append(f"Historical dataset rejected: {misaligned} misaligned candle timestamps")
                return report
            diffs = df["timestamp"].diff().dropna()
            gap_mask = (diffs > pd.Timedelta(minutes=minutes * 1.5)) & (diffs <= pd.Timedelta(hours=6))
            if symbol.upper() in ("XAUUSD", "XAU/USD") and timeframe.upper() == "15M":
                # Dukascopy XAU/USD has a scheduled 1-hour daily maintenance break.
                # Candle-start timestamps therefore have a 75-minute delta at 22:00 UTC
                # in summer or 23:00 UTC in winter; classify it as a session break.
                next_timestamps = df["timestamp"].iloc[1:]
                expected_gold_break = (
                    (diffs == pd.Timedelta(minutes=75)) &
                    next_timestamps.dt.hour.isin([22, 23]) &
                    (next_timestamps.dt.minute == 0)
                )
                report.session_breaks = int(expected_gold_break.sum())
                gap_mask = gap_mask & ~expected_gold_break
            report.gaps_detected = int(gap_mask.sum())
            report.missing_candles = sum(
                max(1, int(round(delta.total_seconds() / (minutes * 60))) - 1)
                for delta in diffs[gap_mask]
            )
            df = only_closed_candles(df, timeframe)
            report.bars_used = len(df)
            if not df.empty:
                report.period_start = str(df.iloc[0]["timestamp"])
                report.period_end = str(df.iloc[-1]["timestamp"])
    report.notes.append("Walk-forward on closed historical candles only; no forming-bar lookahead")
    report.notes.append(f"Walk-forward sampling step: every {step} closed candle(s)")
    report.notes.append(f"Historical data provider: {report.data_provider}; bars: {report.bars_used}")
    report.notes.append("Same-candle SL+TP ambiguity → SL (conservative)")
    report.notes.append("Research tool only — does not claim profitability")

    if df is None or len(df) < window_size + 10:
        report.notes.append("Insufficient data for walk-forward")
        return report

    df = df.reset_index(drop=True)
    cooldown_until = 0

    for end in range(window_size, len(df) - 5, step):
        if end < cooldown_until:
            continue
        window = df.iloc[: end + 1].tail(window_size).copy()
        trade = _window_setup(symbol, window, min_rr=min_rr, timeframe=timeframe)
        if not trade:
            continue

        outcome, exit_px, exit_idx = _simulate_outcome(
            df, end, trade.direction, trade.entry, trade.stop, trade.tp
        )
        trade.result = outcome  # type: ignore
        trade.exit_price = exit_px
        trade.exit_time = str(df.iloc[exit_idx]["timestamp"])
        risk = abs(trade.entry - trade.stop) or 1e-9
        if outcome == "TP":
            trade.r_multiple = abs(trade.tp - trade.entry) / risk
        elif outcome == "SL":
            trade.r_multiple = -1.0
        else:
            if trade.direction == "BUY":
                trade.r_multiple = (exit_px - trade.entry) / risk
            else:
                trade.r_multiple = (trade.entry - exit_px) / risk

        report.trades.append(trade)
        cooldown_until = exit_idx + 1  # no overlapping trades in MVP

    report.total = len(report.trades)
    report.wins = sum(1 for t in report.trades if t.result == "TP")
    report.losses = sum(1 for t in report.trades if t.result == "SL")
    report.expired = sum(1 for t in report.trades if t.result == "EXPIRED")
    decided = report.wins + report.losses
    report.win_rate = (report.wins / decided * 100) if decided else 0.0
    report.net_r = sum(t.r_multiple for t in report.trades)
    report.avg_r = (report.net_r / report.total) if report.total else 0.0
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
    equity = peak = max_drawdown = 0.0
    for trade in report.trades:
        equity += trade.r_multiple
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    report.max_drawdown_r = max_drawdown
    return report
