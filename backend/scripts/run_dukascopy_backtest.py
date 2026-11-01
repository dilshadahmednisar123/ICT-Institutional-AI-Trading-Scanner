"""Run the deterministic ICT walk-forward backtest on a Dukascopy CSV export.

The input must be real Dukascopy historical OHLC data (bid candles). This script
never creates or fills missing market prices.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

# Running this file from backend/scripts does not automatically put backend/ on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.engines.backtest import run_backtest


def load_dukascopy_csv(path: Path, symbol: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    time_column = next((name for name in ("timestamp", "datetime", "date", "time") if name in frame.columns), None)
    if time_column is None:
        raise ValueError(f"No timestamp/date column in {path}; columns={list(frame.columns)}")
    if time_column != "timestamp":
        frame = frame.rename(columns={time_column: "timestamp"})
    required = {"timestamp", "open", "high", "low", "close"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Missing required OHLC columns in {path}: {sorted(required - set(frame.columns))}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    if frame["timestamp"].isna().any():
        raise ValueError(f"Unparseable timestamps in {path}")
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    frame.attrs["provider"] = f"Dukascopy historical bid candles ({symbol} spot/FX dataset)"
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--symbol", required=True, choices=("EURUSD", "XAUUSD"))
    parser.add_argument("--timeframe", default="15M")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    candles = load_dukascopy_csv(args.csv, args.symbol)
    report = run_backtest(
        args.symbol,
        timeframe=args.timeframe,
        limit=len(candles),
        step=20,
        window_size=200,
        historical_data=candles,
        historical_provider="Dukascopy historical bid candles",
    )
    payload = report.to_dict()
    payload["data_source_note"] = (
        "Dukascopy historical bid OHLC; reference dataset, not a broker-specific execution feed. "
        "Spread, commission, slippage and latency are not modelled by this research backtest."
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "symbol": args.symbol,
        "provider": payload["data_provider"],
        "bars": payload["bars_used"],
        "period_start": payload["period_start"],
        "period_end": payload["period_end"],
        "trades": payload["total"],
        "win_rate": payload["win_rate"],
        "net_r": payload["net_r"],
        "profit_factor": payload["profit_factor"],
        "max_drawdown_r": payload["max_drawdown_r"],
        "gaps_detected": payload["gaps_detected"],
        "missing_candles": payload["missing_candles"],
        "notes": payload["notes"],
    }, indent=2))


if __name__ == "__main__":
    main()
