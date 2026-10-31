# ICT Institutional AI Trading Scanner

**Signal-only ICT Institutional Trading Scanner for Forex & Gold.**

> **NO TRADE** is preferred when conditions fail.

**Repo:** https://github.com/dilshadahmednisar123/ICT-Institutional-AI-Trading-Scanner  
**Version:** `0.6.0-ote-judas-news`

## Models Implemented

| Model | Status |
|-------|--------|
| ICT 2022 Mentorship | ✅ |
| Silver Bullet | ✅ |
| Unicorn | ✅ |
| Turtle Soup | ✅ |
| OTE (Optimal Trade Entry) | ✅ |
| Judas Swing | ✅ |

## Core Engines

Structure · FVG · Liquidity · Displacement · Premium/Discount · Order Blocks · Entry/SL/TP · Scoring · Sessions · News Filter · Pipeline · 20-min Scheduler

## Quick Start

```bash
# Backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

- UI: http://localhost:3000  
- API: http://localhost:8000/docs  
- OHLC for charts: `GET /api/v1/ohlc/EURUSD?timeframe=15M&limit=200`  
- Android APK: see `docs/ANDROID_APK.md`

## Philosophy

Liquidity → Raid → Displacement → Structure → PD array → Structural entry → Invalidation stop → Opposing liquidity TP → Min RR → High confluence  
**NO VALID SETUP = NO TRADE**

## Still Pending

- PO3 / AMD / SMT / more models  
- Real Dukascopy / Twelve Data live keys  
- Lightweight Charts UI overlays  
- Redis job store  
- Backtesting  
- Auth + production host  

## Disclaimer

MIT · Educational use · Not financial advice · Trading involves substantial risk of loss.
