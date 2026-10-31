# ICT Institutional AI Trading Scanner

**Signal-only ICT scanner for Forex & Gold.**  
**NO TRADE** when conditions fail.

**Repo:** https://github.com/dilshadahmednisar123/ICT-Institutional-AI-Trading-Scanner  
**Version:** `0.7.0-po3-smt-backtest`

## Models

| Model | Status |
|-------|--------|
| ICT 2022 Mentorship | ✅ |
| Silver Bullet | ✅ |
| Unicorn | ✅ |
| Turtle Soup | ✅ |
| OTE | ✅ |
| Judas Swing | ✅ |
| **PO3 / AMD** | ✅ |
| **SMT Divergence** | ✅ engine |

## Engines

Structure · FVG · Liquidity · Displacement · Premium/Discount · Order Blocks · Entry/SL/TP · Scoring · Sessions · News Filter · **SMT** · **Backtest** · Scheduler · Pipeline

## UI

- Dark institutional Next.js dashboard  
- **Lightweight Charts** candlestick chart (click symbol row to load)  
- Capacitor path for Android APK (`docs/ANDROID_APK.md`)

## Quick Start

```bash
# Backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

- UI http://localhost:3000  
- API http://localhost:8000/docs  
- OHLC `GET /api/v1/ohlc/EURUSD`  
- Backtest `GET /api/v1/backtest/EURUSD?timeframe=15M`

## Philosophy

Liquidity → Raid → Displacement → Structure → PD array → Structural entry → Invalidation stop → Liquidity TP → Min RR  
**NO VALID SETUP = NO TRADE**

## Pending

- Wire real Dukascopy / Twelve Data (API keys)  
- Chart overlays (FVG/OB/levels)  
- Redis job store  
- Full historical walk-forward backtest  
- Auth + production deploy  

## Disclaimer

MIT · Educational · Not financial advice · Trading involves substantial risk of loss.
