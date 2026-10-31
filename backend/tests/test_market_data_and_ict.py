from datetime import datetime, timedelta, timezone

import pandas as pd

import app.data.provider as provider_module
from app.data.provider import (
    AutoDataProvider,
    BaseDataProvider,
    DukascopyHistoricalProvider,
    SyntheticDataProvider,
    only_closed_candles,
)
from app.engines.structure import SwingPoint, detect_bos_choch
from app.engines.liquidity import LiquidityPool, detect_equal_levels, detect_sweeps
from app.engines.fvg import detect_fvgs
from app.engines.premium_discount import build_dealing_range
from app.engines.entry_risk import build_trade_levels
from app.engines.pipeline import analyze_symbol


class StubProvider(BaseDataProvider):
    def get_ohlc(self, symbol, timeframe, start=None, end=None, limit=500):
        return pd.DataFrame()

    def get_latest_price(self, symbol):
        return None


def candle(ts, o, h, l, c):
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": 1}


def test_validator_counts_duplicates_and_intraday_missing_bars():
    current = datetime.now(timezone.utc)
    now = current.replace(minute=(current.minute // 15) * 15, second=0, microsecond=0)
    rows = [
        candle(now - timedelta(minutes=90), 1.1, 1.101, 1.099, 1.100),
        candle(now - timedelta(minutes=75), 1.1, 1.101, 1.099, 1.100),
        candle(now - timedelta(minutes=75), 1.1, 1.102, 1.098, 1.101),
        candle(now - timedelta(minutes=30), 1.1, 1.101, 1.099, 1.100),
        candle(now - timedelta(minutes=15), 1.1, 1.101, 1.099, 1.100),
    ]
    frame = pd.DataFrame(rows)
    frame.attrs["provider"] = "fixture-feed"
    report = StubProvider().validate(frame, "EURUSD", "15M")
    assert report.is_valid
    assert report.duplicate_candles == 1
    assert report.gaps_detected == 1
    assert report.missing_candles == 2
    assert report.provider == "fixture-feed"


def test_invalid_ohlc_is_rejected():
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    frame = pd.DataFrame([candle(now, 10, 9, 8, 10.5)])
    report = StubProvider().validate(frame, "EURUSD", "1M")
    assert not report.is_valid
    assert report.market_status == "invalid"


def test_production_auto_provider_never_selects_synthetic():
    assert isinstance(AutoDataProvider(), BaseDataProvider)
    assert not isinstance(AutoDataProvider(), SyntheticDataProvider)


def test_unimplemented_dukascopy_returns_unavailable_not_synthetic():
    frame = DukascopyHistoricalProvider().get_ohlc("EURUSD", "15M", limit=10)
    assert frame.empty


def test_equal_highs_and_equal_lows_are_classified_as_bsl_and_ssl():
    now = datetime.now(timezone.utc)
    swings = [
        SwingPoint(1.10000, now, "high", index=2),
        SwingPoint(1.10005, now + timedelta(minutes=15), "high", index=8),
        SwingPoint(1.09000, now, "low", index=4),
        SwingPoint(1.09004, now + timedelta(minutes=15), "low", index=10),
    ]
    pools = detect_equal_levels(swings, tolerance_pct=0.00015)
    assert any(p.kind == "equal_highs" and p.side == "BSL" for p in pools)
    assert any(p.kind == "equal_lows" and p.side == "SSL" for p in pools)


def test_ssl_sweep_requires_reclaim_and_marks_bullish():
    now = datetime.now(timezone.utc)
    frame = pd.DataFrame([
        candle(now, 1.0010, 1.0020, 1.0005, 1.0010),
        candle(now + timedelta(minutes=15), 1.0010, 1.0015, 0.9990, 1.0005),
        candle(now + timedelta(minutes=30), 1.0005, 1.0020, 1.0000, 1.0015),
    ], index=[41, 42, 43])
    pool = LiquidityPool(price=1.0000, side="SSL", kind="equal_lows", strength=80)
    sweeps = detect_sweeps(frame, [pool])
    assert sweeps
    assert sweeps[0].side == "bullish"
    assert sweeps[0].reclaim_confirmed


def test_bsl_sweep_requires_rejection_and_marks_bearish():
    now = datetime.now(timezone.utc)
    frame = pd.DataFrame([
        candle(now, 1.0010, 1.0020, 1.0005, 1.0010),
        candle(now + timedelta(minutes=15), 1.0010, 1.0030, 1.0005, 1.0015),
        candle(now + timedelta(minutes=30), 1.0015, 1.0020, 1.0000, 1.0005),
    ], index=[101, 102, 103])
    pool = LiquidityPool(price=1.0020, side="BSL", kind="equal_highs", strength=80)
    sweeps = detect_sweeps(frame, [pool])
    assert sweeps
    assert sweeps[0].side == "bearish"
    assert sweeps[0].reclaim_confirmed


def test_bullish_fvg_uses_three_candle_imbalance():
    now = datetime.now(timezone.utc)
    frame = pd.DataFrame([
        candle(now, 10.0, 10.5, 9.8, 10.4),
        candle(now + timedelta(minutes=15), 10.4, 11.2, 10.3, 11.1),
        candle(now + timedelta(minutes=30), 11.0, 11.5, 10.8, 11.3),
    ], index=[201, 202, 203])
    fvgs = detect_fvgs(frame)
    assert any(f.direction == "bullish" and f.lower == 10.5 and f.upper == 10.8 for f in fvgs)


def test_dealing_range_and_premium_discount_equilibrium():
    now = datetime.now(timezone.utc)
    swings = [
        SwingPoint(110.0, now, "high", strength="intermediate", index=10),
        SwingPoint(90.0, now, "low", strength="intermediate", index=12),
    ]
    dealing = build_dealing_range(swings)
    assert dealing is not None
    assert dealing.equilibrium == 100.0
    assert dealing.classify(105.0) == "premium"
    assert dealing.classify(95.0) == "discount"


def test_structural_stop_and_opposing_liquidity_target_rr():
    target = LiquidityPool(price=1.1050, side="BSL", kind="equal_highs", strength=90)
    levels = build_trade_levels(
        direction="BUY",
        symbol="EURUSD",
        current_price=1.1000,
        entry_price=1.1010,
        entry_type="FVG_MIDPOINT",
        invalidation_price=1.0990,
        liquidity_pools=[target],
        atr=0.0010,
    )
    assert levels.valid
    assert levels.stop_loss < levels.entry_price < levels.primary_tp
    assert levels.risk_reward > 0




def test_forming_candle_is_excluded_from_confirmed_analysis():
    now = datetime(2026, 10, 31, 16, 0, tzinfo=timezone.utc)
    frame = pd.DataFrame([
        candle(now - timedelta(minutes=15), 1.1, 1.101, 1.099, 1.1),
        candle(now, 1.1, 1.102, 1.099, 1.101),
    ])
    closed = only_closed_candles(frame, "15M", now=now)
    assert len(closed) == 1
    assert closed.iloc[-1]["timestamp"] == now - timedelta(minutes=15)


def test_timeframe_misaligned_candles_are_rejected():
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    frame = pd.DataFrame([candle(now + timedelta(minutes=1), 1.1, 1.101, 1.099, 1.1)])
    report = StubProvider().validate(frame, "EURUSD", "15M")
    assert not report.is_valid
    assert report.misaligned_candles == 1
    assert report.market_status == "invalid"


def test_market_closed_blocks_even_recent_candle_setups(monkeypatch):
    fixed_now = datetime(2026, 10, 31, 16, 0, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz else fixed_now.replace(tzinfo=None)

    monkeypatch.setattr(provider_module, "datetime", FrozenDateTime)
    rows = []
    for i in range(100):
        ts = fixed_now - timedelta(minutes=15 * (100 - i))
        rows.append(candle(ts, 1.1, 1.101, 1.099, 1.1))
    frame = pd.DataFrame(rows)

    class RecentHistoricalProvider(StubProvider):
        def get_ohlc(self, symbol, timeframe, start=None, end=None, limit=500):
            return frame

    result = analyze_symbol("EURUSD", timeframe="15M", provider=RecentHistoricalProvider())
    assert result.setup_status == "NO_SETUP"
    assert result.data_quality["market_status"] == "market_closed"
    assert any("MARKET CLOSED" in note for note in result.notes)


def test_bos_is_close_confirmed_after_confirmed_swing():
    now = datetime.now(timezone.utc)
    frame = pd.DataFrame([
        candle(now, 9.0, 10.0, 8.8, 9.2),
        candle(now + timedelta(minutes=15), 9.2, 9.7, 8.9, 9.4),
        candle(now + timedelta(minutes=30), 9.4, 9.6, 8.5, 8.8),
        candle(now + timedelta(minutes=45), 8.8, 9.5, 8.7, 9.3),
        candle(now + timedelta(minutes=60), 9.3, 10.2, 9.2, 10.1),
    ])
    swings = [
        SwingPoint(10.0, now, "high", index=0),
        SwingPoint(8.5, now + timedelta(minutes=30), "low", index=2),
    ]
    events = detect_bos_choch(frame, swings, timeframe="15M")
    assert any(e.event_type == "BOS" and e.direction == "bullish" and e.confirmed_by_close for e in events)
