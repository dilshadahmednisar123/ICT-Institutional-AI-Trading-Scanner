# ICT Institutional AI Trading Scanner

**Signal-only ICT scanner for Forex & Gold.**  
**NO TRADE** when conditions fail.

**Repo:** https://github.com/dilshadahmednisar123/ICT-Institutional-AI-Trading-Scanner  
**Version:** `0.8.0-live-overlays`

## Models

2022 · Silver Bullet · Unicorn · Turtle Soup · OTE · Judas · **PO3/AMD** · **SMT**

## Highlights

- Auto data provider: uses **Twelve Data** when `TWELVE_DATA_API_KEY` is set, otherwise Dukascopy placeholder / synthetic offline
- Chart **Entry / SL / TP / EQ** price-line overlays
- SMT divergence column on dashboard
- Docker Compose for backend
- Backtest endpoint + 20-min scheduler
- Android APK path via Capacitor

## Quick Start

```bash
# Optional live data
export TWELVE_DATA_API_KEY=your_key

cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

cd frontend && npm install && npm run dev
```

Or: `docker compose up backend`

- UI http://localhost:3000  
- API http://localhost:8000/docs  
- Backtest `GET /api/v1/backtest/EURUSD`  
- OHLC `GET /api/v1/ohlc/EURUSD`

## Philosophy

Liquidity → Raid → Displacement → Structure → PD array → Structural entry → Invalidation stop → Liquidity TP  
**NO VALID SETUP = NO TRADE**

## Still optional / next

- Redis job store for multi-worker scheduler  
- Full walk-forward historical backtest  
- Auth  
- Production host + HTTPS  

## Disclaimer

MIT · Educational · Not financial advice · Trading involves substantial risk of loss.
