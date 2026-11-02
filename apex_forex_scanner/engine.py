import asyncio
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("apex")

PAIRS = [
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "USDCAD=X", "AUDUSD=X", "NZDUSD=X",
    "EURJPY=X", "GBPJPY=X", "AUDJPY=X", "CADJPY=X", "CHFJPY=X", "NZDJPY=X",
    "EURAUD=X", "EURNZD=X", "EURGBP=X", "EURCHF=X", "EURCAD=X",
    "GBPAUD=X", "GBPNZD=X", "GBPCAD=X", "GBPCHF=X",
    "AUDNZD=X", "AUDCAD=X", "AUDCHF=X", "NZDCAD=X", "NZDCHF=X", "CADCHF=X"
]

def add_indicators(df):
    df = df.copy()
    close = df["Close"]
    df["EMA_20"] = close.ewm(span=20, adjust=False, min_periods=20).mean()
    df["EMA_50"] = close.ewm(span=50, adjust=False, min_periods=50).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))
    return df

def fetch_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        d1 = ticker.history(period="6mo", interval="1d", auto_adjust=False)
        h1 = ticker.history(period="60d", interval="1h", auto_adjust=False)
        m15 = ticker.history(period="5d", interval="15m", auto_adjust=False)
        if d1.empty or h1.empty or m15.empty:
            return None
        h4 = h1.resample("4h").agg({
            "Open": "first", "High": "max", "Low": "min",
            "Close": "last", "Volume": "sum"
        }).dropna(subset=["Open", "High", "Low", "Close"])
        frames = {"1D": d1, "4H": h4, "1H": h1, "15M": m15}
        frames = {k: add_indicators(v) for k, v in frames.items()}
        price = float(m15["Close"].dropna().iloc[-1])
        return {**frames, "current_price": price}
    except Exception:
        log.exception("Yahoo Finance fetch failed for %s", symbol)
        return None

def get_structure(df):
    if df is None or len(df) < 50:
        return "RANGING"
    row = df.iloc[-1]
    if pd.isna(row["EMA_20"]) or pd.isna(row["EMA_50"]):
        return "RANGING"
    if row["Close"] > row["EMA_20"] > row["EMA_50"]:
        return "BULLISH"
    if row["Close"] < row["EMA_20"] < row["EMA_50"]:
        return "BEARISH"
    return "RANGING"

def find_swing_levels(df, window=5):
    if len(df) < window:
        return np.array([]), np.array([])
    highs = df["High"].rolling(window=window, center=True).max().eq(df["High"])
    lows = df["Low"].rolling(window=window, center=True).min().eq(df["Low"])
    # Ignore the most recent bars because a centred swing is not confirmed until
    # bars have printed on both sides.
    highs.iloc[-2:] = False
    lows.iloc[-2:] = False
    return df.loc[highs, "High"].dropna().to_numpy(), df.loc[lows, "Low"].dropna().to_numpy()

def calculate_setup(symbol, data):
    if not data:
        return None
    price = data["current_price"]
    t1d = get_structure(data["1D"])
    t4h = get_structure(data["4H"])
    t1h = get_structure(data["1H"])
    if t1d != t4h or t1d == "RANGING":
        return None

    direction = "BUY" if t1d == "BULLISH" else "SELL"
    score = 3.0
    if t1h == t1d:
        score += 1.0
    elif t1h != "RANGING":
        score -= 1.0

    highs, lows = find_swing_levels(data["1H"])
    levels = highs if direction == "SELL" else lows
    if len(levels) == 0:
        return None
    entry = float(min(levels, key=lambda x: abs(float(x) - price)))
    near_pct = abs(price - entry) / price if price else 1
    score += 3.0 if near_pct <= 0.001 else 1.0

    # Percentage-based protective distance; pip conversion handles JPY quotes.
    distance = entry * 0.0015
    if direction == "SELL":
        stop = entry + distance
        tp1, tp2, tp3 = entry - distance*1.5, entry - distance*4, entry - distance*6
    else:
        stop = entry - distance
        tp1, tp2, tp3 = entry + distance*1.5, entry + distance*4, entry + distance*6

    rr = abs(tp2 - entry) / distance if distance else 0
    score += 3.0 if rr >= 4 else 2.0 if rr >= 2 else 1.0 if rr >= 1.5 else 0
    score = min(10.0, max(0.0, score))
    pip_size = 0.01 if "JPY" in symbol else 0.0001
    decimals = 3 if "JPY" in symbol else 5

    return {
        "pair": symbol.replace("=X", ""),
        "direction": direction,
        "score": round(score, 1),
        "confidence": "HIGH" if score >= 8.5 else "MEDIUM" if score >= 8 else "LOW",
        "entry": round(entry, decimals),
        "current_price": round(price, decimals),
        "stop_loss": round(stop, decimals),
        "risk_pips": round(abs(entry-stop)/pip_size, 1),
        "tp1": round(tp1, decimals),
        "tp2": round(tp2, decimals),
        "tp3": round(tp3, decimals),
        "rr": f"1:{rr:.1f}",
        "trend_1d": t1d,
        "trend_4h": t4h,
        "trend_1h": t1h,
        "setup_type": "EMA trend + swing-level pullback",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

async def scan_market():
    semaphore = asyncio.Semaphore(4)

    async def scan_one(pair):
        async with semaphore:
            data = await asyncio.to_thread(fetch_data, pair)
            if not data:
                return None
            setup = calculate_setup(pair, data)
            return setup if setup and setup["score"] >= 7.0 else None

    scanned = await asyncio.gather(*(scan_one(pair) for pair in PAIRS), return_exceptions=True)
    results = []
    for item in scanned:
        if isinstance(item, Exception):
            log.error("Pair scan error: %s", item)
        elif item:
            results.append(item)
    results.sort(key=lambda x: x["score"], reverse=True)
    return {
        "results": results,
        "pairs_analyzed": len(PAIRS),
        "setups_found": len(results),
        "last_scan": datetime.now(timezone.utc).isoformat(),
        "status": "Complete"
    }
