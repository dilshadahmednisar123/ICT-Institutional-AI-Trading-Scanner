"""Extra API helpers — backtest endpoint registration."""

from fastapi import APIRouter, Query
from .engines.backtest import run_backtest

router = APIRouter()


@router.get("/api/v1/backtest/{symbol}")
def backtest_symbol(
    symbol: str,
    timeframe: str = Query("15M"),
    limit: int = Query(400, ge=100, le=2000),
):
    report = run_backtest(symbol.upper(), timeframe=timeframe, limit=limit)
    return report.to_dict()
