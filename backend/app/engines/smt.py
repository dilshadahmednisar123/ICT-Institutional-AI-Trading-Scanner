"""
ICT SMT Divergence Engine

Compares correlated instruments on synchronized swing points.

Bullish SMT: one instrument makes a lower low while the correlated instrument fails to.
Bearish SMT: one instrument makes a higher high while the correlated instrument fails to.

Default pairs (configurable):
- EURUSD vs GBPUSD
- AUDUSD vs NZDUSD
- XAUUSD vs (optional related — only when justified)

Does not assume permanent correlation. Returns UNAVAILABLE when data is missing.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Literal, Tuple
import pandas as pd

from .structure import find_swing_points, SwingPoint

DEFAULT_CORRELATIONS: Dict[str, str] = {
    "EURUSD": "GBPUSD",
    "GBPUSD": "EURUSD",
    "AUDUSD": "NZDUSD",
    "NZDUSD": "AUDUSD",
    "EURJPY": "GBPJPY",
    "GBPJPY": "EURJPY",
}


@dataclass
class SMTResult:
    symbol: str
    correlated: Optional[str]
    available: bool
    divergence: Optional[Literal["bullish", "bearish"]]
    detail: str
    score: float = 0.0  # 0-5 for confluence weight

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "correlated": self.correlated,
            "available": self.available,
            "divergence": self.divergence,
            "detail": self.detail,
            "score": self.score,
        }


def _last_swings(swings: List[SwingPoint], kind: str, n: int = 3) -> List[SwingPoint]:
    pts = [s for s in swings if s.kind == kind]
    return pts[-n:] if pts else []


def detect_smt(
    symbol: str,
    df_primary: pd.DataFrame,
    df_correlated: Optional[pd.DataFrame],
    correlated_symbol: Optional[str] = None,
) -> SMTResult:
    corr = correlated_symbol or DEFAULT_CORRELATIONS.get(symbol.upper())

    if corr is None:
        return SMTResult(
            symbol=symbol,
            correlated=None,
            available=False,
            divergence=None,
            detail="No default correlated instrument configured",
            score=0.0,
        )

    if df_correlated is None or df_correlated.empty:
        return SMTResult(
            symbol=symbol,
            correlated=corr,
            available=False,
            divergence=None,
            detail="SMT UNAVAILABLE — correlated series missing",
            score=0.0,
        )

    swings_a = find_swing_points(df_primary, left=3, right=3)
    swings_b = find_swing_points(df_correlated, left=3, right=3)

    lows_a = _last_swings(swings_a, "low", 3)
    lows_b = _last_swings(swings_b, "low", 3)
    highs_a = _last_swings(swings_a, "high", 3)
    highs_b = _last_swings(swings_b, "high", 3)

    # Bullish SMT: A makes lower low, B does not
    if len(lows_a) >= 2 and len(lows_b) >= 2:
        a_ll = lows_a[-1].price < lows_a[-2].price
        b_ll = lows_b[-1].price < lows_b[-2].price
        if a_ll and not b_ll:
            return SMTResult(
                symbol=symbol,
                correlated=corr,
                available=True,
                divergence="bullish",
                detail=f"{symbol} lower low while {corr} failed to make lower low",
                score=5.0,
            )
        if b_ll and not a_ll:
            # Relative strength in primary
            return SMTResult(
                symbol=symbol,
                correlated=corr,
                available=True,
                divergence="bullish",
                detail=f"{corr} lower low while {symbol} held higher low (relative strength)",
                score=4.0,
            )

    # Bearish SMT: A makes higher high, B does not
    if len(highs_a) >= 2 and len(highs_b) >= 2:
        a_hh = highs_a[-1].price > highs_a[-2].price
        b_hh = highs_b[-1].price > highs_b[-2].price
        if a_hh and not b_hh:
            return SMTResult(
                symbol=symbol,
                correlated=corr,
                available=True,
                divergence="bearish",
                detail=f"{symbol} higher high while {corr} failed to make higher high",
                score=5.0,
            )
        if b_hh and not a_hh:
            return SMTResult(
                symbol=symbol,
                correlated=corr,
                available=True,
                divergence="bearish",
                detail=f"{corr} higher high while {symbol} held lower high (relative weakness)",
                score=4.0,
            )

    return SMTResult(
        symbol=symbol,
        correlated=corr,
        available=True,
        divergence=None,
        detail="No SMT divergence on recent swings",
        score=0.0,
    )
