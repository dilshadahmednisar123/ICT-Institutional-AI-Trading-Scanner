# ICT Institutional AI Trading Scanner

**Signal-only ICT (Inner Circle Trader) Institutional Trading Scanner for Forex & Gold.**

> Highly selective. **NO TRADE** is the preferred outcome when conditions are not met.

**Repo:** https://github.com/dilshadahmednisar123/ICT-Institutional-AI-Trading-Scanner

## Current Version: `0.5.0-multi-model`

### Implemented

| Module | Status |
|--------|--------|
| Data Provider + quality checks | ✅ |
| Structure / FVG / Liquidity / Displacement | ✅ |
| Premium-Discount / Order Blocks | ✅ |
| Entry + Structural SL + Liquidity TP | ✅ |
| 100-point Scoring | ✅ |
| Session Engine + Silver Bullet windows | ✅ |
| **ICT 2022 Mentorship Model** | ✅ |
| **Silver Bullet Model** | ✅ |
| **Unicorn Model** | ✅ |
| **Turtle Soup Model** | ✅ |
| 20-min APScheduler + controls | ✅ |
| FastAPI full endpoints | ✅ |
| Next.js dark institutional dashboard | ✅ |
| Capacitor Android APK path + docs | ✅ |

### Still Pending

- Remaining models (OTE, Judas, PO3, AMD, Breaker-only, FVG continuation, SMT, etc.)
- Real live Dukascopy / Twelve Data wiring (keys required)
- Lightweight Charts overlays
- Redis/SQLAlchemy persistent job store
- News calendar filter
- Backtesting engine
- Auth + production deployment

## Quick Start

### Backend
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install && npm run dev
```

- Dashboard: http://localhost:3000  
- API docs: http://localhost:8000/docs  

### Android APK
See [docs/ANDROID_APK.md](docs/ANDROID_APK.md) for Capacitor build steps.

### Scheduler
```
POST /api/v1/scheduler/start
POST /api/v1/scheduler/pause | resume | stop
GET  /api/v1/scheduler/status
```

## Philosophy

1. Liquidity first  
2. Raid + Displacement + Structure  
3. Valid PD array  
4. Precise structural entry  
5. Stop beyond invalidation  
6. Target real opposing liquidity  
7. Minimum RR filter  
8. High confluence required  
9. **NO VALID SETUP = NO TRADE**

## License & Disclaimer

MIT — educational / research use.  
**Trading involves substantial risk of loss. This is not financial advice.**
