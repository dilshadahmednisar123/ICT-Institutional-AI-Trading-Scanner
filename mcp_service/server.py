"""LIQUIDITY NEXUS read-only MCP server. Data source: biquote public MT5 feed."""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

BASE = os.getenv("BIQUOTE_BASE_URL", "https://biquote.io").rstrip("/")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT_SECONDS", "15"))
MAX_BARS = 1000
ALLOWED_SYMBOLS = {
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
    "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD",
    "AUDJPY", "AUDNZD", "AUDCAD", "AUDCHF", "NZDJPY", "NZDCAD",
    "NZDCHF", "CADJPY", "CADCHF", "CHFJPY", "XAUUSD",
}
INTERVALS = {"1M": "1m", "5M": "5m", "15M": "15m", "30M": "30m",
             "1H": "1h", "4H": "4h", "1D": "1d"}

mcp = FastMCP("LIQUIDITY NEXUS", stateless_http=True, json_response=True,
              instructions="Read-only Forex and XAUUSD market research. Never claim institutional order flow, never invent prices or candles, and never place trades.")

async def get_json(path: str, params: dict[str, Any] | None = None) -> Any:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers={"User-Agent": "LiquidityNexus-MCP/1.0"}) as client:
        response = await client.get(f"{BASE}{path}", params=params)
        response.raise_for_status()
        return response.json()

def validate_symbol(symbol: str) -> str:
    symbol = symbol.upper().replace("/", "").strip()
    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError(f"Unsupported symbol: {symbol}. Use an allowed Forex pair or XAUUSD.")
    return symbol

def parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

@mcp.tool()
async def market_data_status() -> dict:
    """Check upstream feed health and confirm whether the source currently reports itself healthy."""
    health = await get_json("/health")
    return {"provider": "biquote MT5 feed", "health": health,
            "important_limitations": ["Broker/CFD quotes, not a consolidated exchange tape",
            "FX/CFD volume is not real traded volume", "Check quoteAgeSeconds and marketState before treating a quote as live"]}

@mcp.tool()
async def get_market_quote(symbol: str) -> dict:
    """Get the latest bid/ask/mid quote for a Forex pair or XAUUSD, including freshness and market state."""
    symbol = validate_symbol(symbol)
    quote = await get_json(f"/api/{symbol}", {"allowStale": "true"})
    age = quote.get("quoteAgeSeconds")
    return {"symbol": symbol, "provider": quote.get("source", "biquote MT5"),
            "bid": quote.get("bid"), "ask": quote.get("ask"), "mid": quote.get("mid"),
            "spread": quote.get("spread"), "timestamp_utc": quote.get("timestamp"),
            "market_state": quote.get("marketState"), "stale": quote.get("stale"),
            "quote_age_seconds": age,
            "usable_as_live": quote.get("marketState") == "open" and quote.get("stale") is False and isinstance(age, (int, float)) and age <= 60,
            "warning": "Indicative broker/CFD quote; not a guaranteed executable price."}

@mcp.tool()
async def get_ohlc_candles(symbol: str, timeframe: str = "15M", limit: int = 300) -> dict:
    """Retrieve real OHLC candles for Forex or XAUUSD. Open/forming bars are removed. Timeframes: 1M,5M,15M,30M,1H,4H,1D."""
    symbol = validate_symbol(symbol)
    tf = timeframe.upper()
    if tf not in INTERVALS:
        raise ValueError(f"Unsupported timeframe: {tf}. Use {', '.join(INTERVALS)}.")
    if not 10 <= int(limit) <= MAX_BARS:
        raise ValueError("limit must be between 10 and 1000")
    data = await get_json(f"/api/{symbol}/ohlc", {"interval": INTERVALS[tf], "limit": int(limit)})
    bars = data.get("bars", []) if isinstance(data, dict) else []
    closed = [b for b in bars if not b.get("isOpen", False)]
    closed.sort(key=lambda b: b.get("openTime", ""))
    if not closed:
        return {"symbol": symbol, "timeframe": tf, "candles": [], "status": "DATA_UNAVAILABLE",
                "message": "Provider returned no closed candles. No fallback or synthetic data was used."}
    last = parse_time(closed[-1]["openTime"])
    tf_mins = {"1M":1,"5M":5,"15M":15,"30M":30,"1H":60,"4H":240,"1D":1440}[tf]
    age = max(0, (datetime.now(timezone.utc) - (last + timedelta(minutes=tf_mins))).total_seconds())
    return {"symbol": symbol, "timeframe": tf, "provider": "biquote MT5 feed",
            "status": "OK" if age <= max(180, tf_mins * 2.5 * 60) else "STALE",
            "closed_candle_count": len(closed), "last_closed_candle_open_utc": last.isoformat(),
            "last_candle_age_seconds": int(age), "candles": [
                {"time": b["openTime"], "open": float(b["open"]), "high": float(b["high"]),
                 "low": float(b["low"]), "close": float(b["close"]),
                 "volume": float(b.get("volume") or 0), "tick_volume": b.get("tickVolume")}
                for b in closed[-int(limit):]],
            "volume_warning": "The provider documents FX/CFD volume as zero/not real traded volume. Do not use it as institutional volume confirmation."}

@mcp.tool()
async def scan_ict_smc(symbol: str, timeframe: str = "15M", limit: int = 300) -> dict:
    """Run transparent candle-based ICT/SMC checks: swing structure, BOS/CHOCH proxy, FVGs and liquidity sweeps. This is heuristic analysis, not proof of institutional activity."""
    payload = await get_ohlc_candles(symbol, timeframe, limit)
    bars = payload.get("candles", [])
    if len(bars) < 30 or payload.get("status") != "OK":
        return {"symbol": payload.get("symbol", symbol.upper()), "timeframe": timeframe.upper(),
                "status": "NO_SETUP", "reason": "Insufficient fresh closed candles; no signal generated.",
                "data": payload}
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    swings_high = [(i, highs[i]) for i in range(2, len(bars)-2)
                   if highs[i] > max(highs[i-2:i]) and highs[i] >= max(highs[i+1:i+3])]
    swings_low = [(i, lows[i]) for i in range(2, len(bars)-2)
                  if lows[i] < min(lows[i-2:i]) and lows[i] <= min(lows[i+1:i+3])]
    last_close = closes[-1]
    last = bars[-1]
    prior_high = max(highs[-21:-1])
    prior_low = min(lows[-21:-1])
    sweep_high = last["high"] > prior_high and last_close < prior_high
    sweep_low = last["low"] < prior_low and last_close > prior_low
    fvgs = []
    for i in range(2, len(bars)):
        left, right = bars[i-2], bars[i]
        if right["low"] > left["high"]:
            fvgs.append({"type":"bullish", "lower":left["high"], "upper":right["low"], "formed_at":right["time"]})
        if right["high"] < left["low"]:
            fvgs.append({"type":"bearish", "lower":right["high"], "upper":left["low"], "formed_at":right["time"]})
    latest_high = swings_high[-1][1] if swings_high else None
    latest_low = swings_low[-1][1] if swings_low else None
    bos = "bullish" if latest_high is not None and last_close > latest_high else ("bearish" if latest_low is not None and last_close < latest_low else "none")
    dealing_high, dealing_low = max(highs[-50:]), min(lows[-50:])
    midpoint = (dealing_high + dealing_low) / 2
    location = "discount" if last_close < midpoint else "premium"
    return {"symbol": payload["symbol"], "timeframe": timeframe.upper(), "status":"ANALYZED",
            "provider":payload["provider"], "last_close":last_close,
            "market_structure_proxy":{"latest_swing_high":latest_high,"latest_swing_low":latest_low,"bos_proxy":bos},
            "liquidity":{"buy_side_sweep":sweep_high,"sell_side_sweep":sweep_low,
                         "reference_high_20":prior_high,"reference_low_20":prior_low},
            "fair_value_gaps":fvgs[-10:], "premium_discount":{"range_high":dealing_high,
            "range_low":dealing_low,"equilibrium":midpoint,"price_location":location},
            "displacement_proxy":"not_calculated",
            "setup_decision":"NO_SETUP" if not (sweep_high or sweep_low) or bos == "none" else "REVIEW_REQUIRED",
            "limitations":["Swing/BOS/sweep/FVG are deterministic candle heuristics, not verified institutional order flow.",
            "A sweep and BOS alone are insufficient for an entry; require HTF context, displacement, retracement and risk validation.",
            "No calibrated win probability is produced. No trade is placed."]}

@mcp.tool()
async def get_high_impact_calendar(days_ahead: int = 7, limit: int = 100) -> list:
    """Retrieve high-impact upcoming economic events. Times are UTC; convert to IST when presenting."""
    if not 1 <= days_ahead <= 30 or not 1 <= limit <= 500:
        raise ValueError("days_ahead must be 1-30 and limit 1-500")
    now = datetime.now(timezone.utc)
    data = await get_json("/api/calendar", {"from": now.isoformat(), "to": (now + timedelta(days=days_ahead)).isoformat(),
                                              "importance":"high", "limit":limit})
    return data if isinstance(data, list) else data.get("events", [])

@mcp.tool()
async def list_supported_instruments() -> dict:
    """List supported LIQUIDITY NEXUS Forex pairs and Gold instrument identifiers."""
    active = await get_json("/api/active")
    names = {str(x.get("name","")).upper() for x in active if isinstance(x, dict)}
    supported = sorted(ALLOWED_SYMBOLS & names)
    return {"provider":"biquote", "available_now":supported,
            "configured_symbols":sorted(ALLOWED_SYMBOLS),
            "not_currently_quoting":sorted(ALLOWED_SYMBOLS - names)}

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
