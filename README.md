# ICT Institutional AI Trading Scanner

**Signal-only ICT (Inner Circle Trader) Institutional Trading Scanner for Forex & Gold.**

> Highly selective. **NO TRADE** is the preferred outcome when conditions are not met.

**Repo:** https://github.com/dilshadahmednisar123/ICT-Institutional-AI-Trading-Scanner

## Current Version: `0.4.0-sessions-scheduler`

### Implemented

| Module | Status |
|--------|--------|
| Data Provider + quality checks | ✅ |
| Swing / Structure / BOS | ✅ |
| Fair Value Gaps + CE | ✅ |
| Liquidity (BSL/SSL, sweeps, ranking) | ✅ |
| Displacement | ✅ |
| Premium / Discount / Equilibrium | ✅ |
| Order Blocks + Breakers | ✅ |
| Entry + Structural SL + Liquidity TP | ✅ |
| 100-point Confluence Scoring | ✅ |
| **ICT 2022 Mentorship Model** | ✅ |
| **ICT Silver Bullet Model** | ✅ |
| **Session Engine** (Asian / London / NY + SB windows) | ✅ |
| **20-minute APScheduler** + start/stop/pause/resume | ✅ |
| FastAPI with full endpoints | ✅ |
| **Frontend dashboard** (Next.js + Tailwind dark institutional) | ✅ |

### Still Pending

- Remaining ICT models (Unicorn, Turtle Soup, OTE, Judas, PO3, etc.)
- Real live market data (API keys required)
- Persistent job store (Redis/SQLAlchemy) for production scheduler
- Charts (Lightweight Charts)
- News filter + SMT
- Backtesting
- Android APK via Capacitor
- Auth + production deployment

## Quick Start

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000  
API docs: http://localhost:8000/docs

### Scheduler
```
POST /api/v1/scheduler/start   {"interval_minutes": 20}
POST /api/v1/scheduler/pause
POST /api/v1/scheduler/resume
POST /api/v1/scheduler/stop
GET  /api/v1/scheduler/status
```

## Philosophy (enforced in code)

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
