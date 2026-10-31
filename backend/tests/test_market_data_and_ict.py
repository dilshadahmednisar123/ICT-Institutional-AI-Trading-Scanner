from datetime import datetime, timedelta, timezone

import pandas as pd

import app.data.provider as provider_module
import app.engines.backtest as backtest_module
from app.data.provider import (
    AutoDataProvider,
    BaseDataProvider,
    DukascopyHistoricalProvider,
    SyntheticDataProvider,
    get_provider,
    only_closed_candles,
    resample_ohlc,
)
from app.engines.structure import SwingPoint, StructureEvent, detect_bos_choch, classify_structure, find_swing_points
from app.engines.liquidity import LiquidityPool, LiquiditySweep, detect_equal_levels, detect_sweeps, rank_targets
from app.engines.fvg import FairValueGap, detect_fvgs
from app.engines.premium_discount import build_dealing_range
from app.engines.entry_risk import build_trade_levels
from app.engines.displacement import DisplacementEvent, detect_displacement
from app.engines.order_blocks import detect_order_blocks
from app.engines.premium_discount import DealingRange
from app.engines.models.ote import evaluate_ote, OTEState
from app.engines.models.ict_2022 import evaluate_ict_2022, ModelState
from app.engines.backtest import _window_setup
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


def test_production_auto_provider_never_selects_synthetic(monkeypatch):
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    provider = AutoDataProvider()
    assert isinstance(provider, BaseDataProvider)
    assert not isinstance(provider, SyntheticDataProvider)
    frame = provider.get_ohlc("EURUSD", "15M", limit=100)
    report = provider.validate(frame, "EURUSD", "15M")
    assert frame.empty
    assert not report.is_valid
    assert "TWELVE_DATA_API_KEY" in report.message


def test_yahoo_provider_is_disabled_for_trading_use():
    provider = get_provider("yahoo")
    frame = provider.get_ohlc("EURUSD", "15M", limit=100)
    assert frame.empty
    assert "not intended for trading" in frame.attrs["error"]



def test_analysis_returns_no_setup_when_licensed_feed_is_not_configured(monkeypatch):
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    result = analyze_symbol("EURUSD", timeframe="15M", provider=AutoDataProvider())
    assert result.setup_status == "NO_SETUP"
    assert result.best_setup is None
    assert result.data_quality["is_valid"] is False
    assert result.data_quality["market_status"] == "unavailable"


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



def test_take_profit_selects_nearest_pool_when_opposing_liquidity_strength_ties():
    nearer = LiquidityPool(price=1.1030, side="BSL", kind="equal_highs", strength=80)
    farther = LiquidityPool(price=1.1050, side="BSL", kind="swing_high", strength=80)
    targets = rank_targets([farther, nearer], current_price=1.1010, direction="BUY")
    assert targets[0] is nearer


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





def test_higher_timeframe_resample_uses_complete_aligned_groups_only():
    start = datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc)
    now = start + timedelta(hours=8)
    rows = []
    for i in range(33):
        ts = start + timedelta(minutes=15 * i)
        price = 1.0 + i * 0.0001
        rows.append(candle(ts, price, price + 0.001, price - 0.001, price + 0.0005))
        rows[-1]["volume"] = 10
    frame = pd.DataFrame(rows)
    frame.attrs["provider"] = "fixture-feed"
    htf = resample_ohlc(frame, "15M", "4H", now=now)
    assert len(htf) == 2
    assert list(htf["timestamp"]) == [start, start + timedelta(hours=4)]
    assert htf.iloc[0]["open"] == rows[0]["open"]
    assert htf.iloc[0]["volume"] == 160
    assert htf.attrs["provider"] == "fixture-feed"


def test_forming_candle_is_excluded_from_confirmed_analysis():
    now = datetime(2026, 10, 31, 16, 0, tzinfo=timezone.utc)
    frame = pd.DataFrame([
        candle(now - timedelta(minutes=15), 1.1, 1.101, 1.099, 1.1),
        candle(now, 1.1, 1.102, 1.099, 1.101),
    ])
    closed = only_closed_candles(frame, "15M", now=now)
    assert len(closed) == 1
    assert closed.iloc[-1]["timestamp"] == now - timedelta(minutes=15)



def test_daily_candles_must_align_to_utc_day_boundary():
    ts = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    frame = pd.DataFrame([candle(ts, 1.1, 1.101, 1.099, 1.1)])
    report = StubProvider().validate(frame, "EURUSD", "1D")
    assert not report.is_valid
    assert report.misaligned_candles == 1


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




def test_swing_points_record_right_side_confirmation_index():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    highs = [10, 11, 12, 20, 12, 11, 10, 11, 12, 13]
    lows = [8, 7, 6, 5, 6, 7, 8, 7, 6, 5]
    frame = pd.DataFrame([
        candle(now + timedelta(minutes=15 * i), 10, highs[i], lows[i], 10)
        for i in range(len(highs))
    ])
    swings = find_swing_points(frame, left=3, right=3)
    pivot = next(s for s in swings if s.index == 3)
    assert pivot.confirmation_index == 6



def test_bos_does_not_use_pivot_before_right_side_confirmation():
    now = datetime.now(timezone.utc)
    frame = pd.DataFrame([
        candle(now, 9.0, 9.5, 8.8, 9.2),
        candle(now + timedelta(minutes=15), 9.2, 10.0, 9.0, 9.5),
        candle(now + timedelta(minutes=30), 9.5, 9.8, 8.0, 9.0),
        candle(now + timedelta(minutes=45), 9.0, 9.7, 8.5, 9.3),
        candle(now + timedelta(minutes=60), 9.3, 10.2, 9.2, 10.1),
        candle(now + timedelta(minutes=75), 10.1, 10.3, 9.8, 10.2),
    ])
    swings = [
        SwingPoint(10.0, now + timedelta(minutes=15), "high", index=1, confirmation_index=4),
        SwingPoint(8.0, now + timedelta(minutes=30), "low", index=2, confirmation_index=5),
    ]
    events = detect_bos_choch(frame, swings, timeframe="15M")
    assert not any(e.direction == "bullish" for e in events)



def test_displacement_detector_confirms_large_directional_candle():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        candle(now + timedelta(minutes=15 * i), 1.1000, 1.1010, 1.0990, 1.1005)
        for i in range(19)
    ]
    rows.append(candle(now + timedelta(minutes=285), 1.1000, 1.1150, 1.0990, 1.1140))
    frame = pd.DataFrame(rows, index=range(300, 320))
    events = detect_displacement(frame, atr_period=14, min_body_ratio=0.60, min_atr_multiple=1.2)
    assert any(e.direction == "bullish" and e.index == 19 and
               e.body_to_range >= 0.60 and e.atr_multiple >= 1.2 for e in events)


def test_higher_timeframe_structure_bias_is_directional():
    now = datetime.now(timezone.utc)
    swings = [
        SwingPoint(10.0, now, "high", index=0),
        SwingPoint(8.0, now + timedelta(minutes=15), "low", index=1),
        SwingPoint(11.0, now + timedelta(minutes=30), "high", index=2),
        SwingPoint(9.0, now + timedelta(minutes=45), "low", index=3),
    ]
    structure = classify_structure(swings)
    assert structure["bias"] == "bullish"


def test_bearish_structure_then_bullish_break_is_choch():
    now = datetime.now(timezone.utc)
    frame = pd.DataFrame([
        candle(now, 9.0, 10.0, 8.8, 9.2),
        candle(now + timedelta(minutes=15), 9.2, 9.7, 8.9, 9.4),
        candle(now + timedelta(minutes=30), 9.4, 9.6, 8.0, 8.8),
        candle(now + timedelta(minutes=45), 8.8, 9.0, 7.5, 8.7),
        candle(now + timedelta(minutes=60), 8.7, 9.8, 8.6, 9.6),
    ])
    swings = [
        SwingPoint(10.0, now, "high", index=0),
        SwingPoint(8.0, now + timedelta(minutes=30), "low", index=2),
        SwingPoint(9.5, now + timedelta(minutes=30), "high", index=2),
        SwingPoint(7.5, now + timedelta(minutes=45), "low", index=3),
    ]
    assert classify_structure(swings)["bias"] == "bearish"
    events = detect_bos_choch(frame, swings, timeframe="15M")
    assert any(e.event_type == "CHOCH" and e.direction == "bullish" and e.confirmed_by_close for e in events)


def test_order_block_mitigation_is_measured_after_formation():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [candle(now + timedelta(minutes=15 * i), 10.0, 10.2, 9.9, 10.1) for i in range(18)]
    rows.append(candle(now + timedelta(minutes=270), 10.2, 10.3, 9.8, 10.0))
    rows.append(candle(now + timedelta(minutes=285), 10.0, 10.9, 9.95, 10.8))
    frame = pd.DataFrame(rows)
    displacement = DisplacementEvent(
        direction="bullish", time=now + timedelta(minutes=285),
        open=10.0, high=10.9, low=9.95, close=10.8, body=0.8,
        range_=0.95, body_to_range=0.84, atr_multiple=1.8,
        quality_score=80, index=19,
    )
    blocks = detect_order_blocks(frame, displacements=[displacement], timeframe="15M")
    assert blocks
    assert blocks[0].direction == "bullish"
    assert blocks[0].mitigation_pct > 0
    assert not blocks[0].invalidated


def test_ote_requires_location_and_two_confluence_factors():
    now = datetime.now(timezone.utc)
    dealing = DealingRange(high=110.0, low=90.0, equilibrium=100.0,
                           levels={0.0: 90.0, 0.5: 100.0, 1.0: 110.0})
    pool = LiquidityPool(price=95.0, side="SSL", kind="swing_low", strength=80)
    sweep = LiquiditySweep(
        side="bullish", pool=pool, sweep_price=94.0,
        reclaim_confirmed=True, classification="confirmed", time=now,
    )
    target = LiquidityPool(price=105.0, side="BSL", kind="equal_highs", strength=90)
    setups = evaluate_ote(
        symbol="EURUSD", current_price=96.0, htf_bias="bullish",
        dealing_range=dealing, sweeps=[sweep], displacements=[], fvgs=[],
        liquidity_pools=[target], atr=0.5,
    )
    buy = next(s for s in setups if s.direction == "BUY")
    assert buy.state == OTEState.CONFIRMED
    assert buy.levels and buy.levels.valid
    assert buy.levels.stop_loss < buy.levels.entry_price < buy.levels.primary_tp


def _ict_fixture(event_confirmed=True, displacement_after_sweep=True):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    dealing = DealingRange(high=110.0, low=90.0, equilibrium=100.0,
                           levels={0.0: 90.0, 0.5: 100.0, 1.0: 110.0})
    sweep_pool = LiquidityPool(price=95.0, side="SSL", kind="equal_lows", strength=85)
    sweep = LiquiditySweep(
        side="bullish", pool=sweep_pool, sweep_price=94.0,
        reclaim_confirmed=True, classification="confirmed", time=now,
    )
    displacement_time = now + timedelta(minutes=15) if displacement_after_sweep else now - timedelta(minutes=15)
    displacement = DisplacementEvent(
        direction="bullish", time=displacement_time,
        open=94.5, high=96.0, low=94.0, close=95.8, body=1.3,
        range_=2.0, body_to_range=0.65, atr_multiple=1.5,
        quality_score=80, index=20,
    )
    fvg = FairValueGap(
        direction="bullish", upper=95.5, lower=94.5, midpoint=95.0,
        width=1.0, formation_time=now + timedelta(minutes=30),
        timeframe="15M", candle_indices=(20, 21, 22),
    )
    structure = StructureEvent(
        event_type="CHOCH", direction="bullish", price=96.0,
        time=now + timedelta(minutes=30), broken_level=95.0,
        confirmed_by_close=event_confirmed, timeframe="15M",
    )
    target = LiquidityPool(price=105.0, side="BSL", kind="equal_highs", strength=90)
    return dealing, sweep, displacement, fvg, structure, target


def test_ict_2022_confirms_only_full_chronological_sequence():
    dealing, sweep, displacement, fvg, structure, target = _ict_fixture()
    setups = evaluate_ict_2022(
        symbol="EURUSD", current_price=95.0, htf_bias="bullish",
        sweeps=[sweep], displacements=[displacement], fvgs=[fvg],
        order_blocks=[], liquidity_pools=[target], dealing_range=dealing,
        premium_discount="discount", atr=0.5, structure_events=[structure],
    )
    buy = next(s for s in setups if s.direction == "BUY")
    assert buy.state == ModelState.CONFIRMED
    assert buy.levels and buy.levels.valid
    assert buy.levels.primary_tp == 105.0



def test_ict_2022_waits_until_entry_price_is_actually_traded():
    dealing, sweep, displacement, fvg, structure, target = _ict_fixture()
    setups = evaluate_ict_2022(
        symbol="EURUSD", current_price=95.4, htf_bias="bullish",
        sweeps=[sweep], displacements=[displacement], fvgs=[fvg],
        order_blocks=[], liquidity_pools=[target], dealing_range=dealing,
        premium_discount="discount", atr=0.5, structure_events=[structure],
        current_bar_high=95.4, current_bar_low=95.1,
    )
    buy = next(s for s in setups if s.direction == "BUY")
    assert buy.state == ModelState.ENTRY_ZONE_READY


def test_ote_waits_when_705_entry_has_not_been_traded():
    now = datetime.now(timezone.utc)
    dealing = DealingRange(high=110.0, low=90.0, equilibrium=100.0,
                           levels={0.0: 90.0, 0.5: 100.0, 1.0: 110.0})
    pool = LiquidityPool(price=95.0, side="SSL", kind="swing_low", strength=80)
    sweep = LiquiditySweep(
        side="bullish", pool=pool, sweep_price=94.0,
        reclaim_confirmed=True, classification="confirmed", time=now,
    )
    target = LiquidityPool(price=105.0, side="BSL", kind="equal_highs", strength=90)
    setups = evaluate_ote(
        symbol="EURUSD", current_price=96.3, htf_bias="bullish",
        dealing_range=dealing, sweeps=[sweep], displacements=[], fvgs=[],
        liquidity_pools=[target], atr=0.5,
        current_bar_high=96.4, current_bar_low=96.1,
    )
    buy = next(s for s in setups if s.direction == "BUY")
    assert buy.state == OTEState.IN_OTE_ZONE


def test_ict_2022_rejects_unconfirmed_structure_and_pre_sweep_displacement():
    dealing, sweep, displacement, fvg, structure, target = _ict_fixture(event_confirmed=False)
    unconfirmed = evaluate_ict_2022(
        symbol="EURUSD", current_price=95.0, htf_bias="bullish",
        sweeps=[sweep], displacements=[displacement], fvgs=[fvg],
        order_blocks=[], liquidity_pools=[target], dealing_range=dealing,
        premium_discount="discount", atr=0.5, structure_events=[structure],
    )
    assert next(s for s in unconfirmed if s.direction == "BUY").state == ModelState.DISPLACEMENT

    dealing, sweep, displacement, fvg, structure, target = _ict_fixture(displacement_after_sweep=False)
    out_of_order = evaluate_ict_2022(
        symbol="EURUSD", current_price=95.0, htf_bias="bullish",
        sweeps=[sweep], displacements=[displacement], fvgs=[fvg],
        order_blocks=[], liquidity_pools=[target], dealing_range=dealing,
        premium_discount="discount", atr=0.5, structure_events=[structure],
    )
    assert next(s for s in out_of_order if s.direction == "BUY").state == ModelState.SWEEP_OCCURRED




def test_backtest_does_not_substitute_synthetic_or_unlicensed_data_without_key(monkeypatch):
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    report = backtest_module.run_backtest("EURUSD", timeframe="15M", limit=500)
    assert report.bars_used == 0
    assert report.total == 0
    assert "DATA UNAVAILABLE" in report.data_provider


def test_backtest_report_records_real_provider_and_historical_window(monkeypatch):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    frame = pd.DataFrame([
        candle(now + timedelta(minutes=15 * i), 1.1, 1.101, 1.099, 1.1)
        for i in range(220)
    ])
    frame.attrs["provider"] = "fixture-historical-feed"

    class HistoricalProvider(StubProvider):
        def get_ohlc(self, symbol, timeframe, start=None, end=None, limit=500):
            return frame.copy()

    monkeypatch.setattr(backtest_module, "get_provider", lambda name: HistoricalProvider())
    report = backtest_module.run_backtest(
        "EURUSD", timeframe="15M", limit=220, step=20, window_size=200
    )
    payload = report.to_dict()
    assert payload["data_provider"] == "fixture-historical-feed"
    assert payload["bars_used"] == 220
    assert payload["period_start"] == str(frame.iloc[0]["timestamp"])
    assert payload["period_end"] == str(frame.iloc[-1]["timestamp"])


def test_walk_forward_backtest_window_runs_ict_pipeline_without_index_errors():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    frame = pd.DataFrame([
        candle(now + timedelta(minutes=15 * i), 1.1, 1.101, 1.099, 1.1)
        for i in range(200)
    ], index=range(1000, 1200))
    assert _window_setup("EURUSD", frame, timeframe="15M") is None


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
