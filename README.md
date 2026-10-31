# ICT Institutional AI Trading Scanner

**Signal-only ICT (Inner Circle Trader) Institutional Trading Scanner for Forex & Gold.**

> Highly selective. **NO TRADE** is the preferred outcome when conditions are not met.

**Repo:** https://github.com/dilshadahmednisar123/ICT-Institutional-AI-Trading-Scanner

## Current Version: `0.3.0-models`

### Implemented & Wired

| Module | Status |
|--------|--------|
| Data Provider Layer + quality checks | ✅ |
| Swing High/Low (non-repainting) | ✅ |
| Market Structure (HH/HL/LH/LL + BOS) | ✅ |
| Fair Value Gaps + CE + mitigation | ✅ |
| Liquidity (BSL/SSL, Equal Highs/Lows, Sweeps, Ranking) | ✅ |
| Displacement (body/range + ATR quality) | ✅ |
| Premium / Discount / Equilibrium | ✅ |
| Order Blocks + Breaker flagging | ✅ |
| Entry + Structural SL + Liquidity TP | ✅ |
| 100-point Confluence Scoring | ✅ |
| **ICT 2022 Mentorship Model state machine** | ✅ |
| Full Analysis Pipeline | ✅ |
| FastAPI (`/scan`, `/analyze/{symbol}`) | ✅ |

### Still Pending

- Remaining ICT models (Silver Bullet, Unicorn, Turtle Soup, OTE, Judas, PO3, etc.)
- Real live data feed (API keys required)
- Persistent 20-minute scheduler
- Session engine + news filter
- SMT Divergence
- Backtesting engine
- Frontend dashboard + charts
- Android APK (Capacitor/PWA)
- Auth + production deployment

## Quick Start

```bash
git clone https://github.com/dilshadahmednisar123/ICT-Institutional-AI-Trading-Scanner.git
cd ICT-Institutional-AI-Trading-Scanner/backend

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000/docs**

- `POST /api/v1/scan` → `{"symbols": ["EURUSD", "XAUUSD"], "timeframe": "15M"}`
- `GET /api/v1/analyze/EURUSD?timeframe=15M`

## Philosophy (enforced)

1. Liquidity first  
2. Raid + Displacement + Structure  
3. Valid PD array (FVG / OB)  
4. Precise structural entry  
5. Stop beyond invalidation  
6. Target real opposing liquidity  
7. Minimum RR filter  
8. High confluence required  
9. **NO VALID SETUP = NO TRADE**

## Data Notes

Historical path is prepared for free Dukascopy libraries.  
Current runtime uses a controlled synthetic fallback so the full pipeline can be developed and tested offline.  
The system never invents prices for live decisions — missing data returns clear quality flags.

## License & Disclaimer

MIT — educational / research use.  
**Trading involves substantial risk of loss. This is not financial advice.**
