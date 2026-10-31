# ICT Institutional AI Trading Scanner

**Production-oriented AI-powered ICT (Inner Circle Trader) Institutional Trading Scanner for Forex & Gold.**

> Signal-only mode by default. Highly selective. **NO TRADE** is a valid and preferred outcome when conditions are not met.

## Project Status

This repository contains a comprehensive scaffold + core engine implementation based on the full master prompt.  
**Full production readiness requires API keys for live data, persistent hosting, and further calibration of all 16 ICT models.**

### Implemented Core Modules (MVP)
- Market data ingestion framework (Dukascopy historical via free open-source libraries)
- Multi-timeframe OHLC handling
- Swing High / Low detection (configurable pivots)
- Market Structure skeleton (HH/HL/LH/LL, BOS, CHOCH)
- Fair Value Gap (FVG) detection + CE
- Liquidity pool identification skeleton (BSL / SSL)
- Displacement quality scoring
- Premium / Discount / Equilibrium calculation
- Entry / Structural SL / Liquidity-based TP calculation engines (framework)
- Setup scoring framework (100-point heuristic)
- FastAPI backend skeleton with clear endpoints
- Basic responsive dashboard structure
- Environment and Docker scaffolding

### Still requiring significant work for full production
- Complete state machines for all 16 ICT models with chronological confirmation sequences
- Real-time / near-real-time live feed integration (user must supply keys)
- Persistent 20-minute production scheduler (Celery + Redis or equivalent)
- Full realistic backtesting engine with spread/slippage/ambiguity rules
- Android APK packaging (path via Capacitor / PWA provided)
- News / economic calendar filter
- Full SMT divergence across correlated instruments
- Production-grade error handling, monitoring, and auth

## Architecture

```
ICT-Institutional-AI-Trading-Scanner/
├── backend/                 # Python FastAPI + analysis engines
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── core/
│   │   ├── engines/         # ICT concept detectors
│   │   ├── models/          # Pydantic + DB models
│   │   ├── data/            # Data providers & validation
│   │   └── scheduler/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                # Next.js + Tailwind (dark institutional UI)
├── shared/
├── docs/
├── tests/
├── .env.example
└── docker-compose.yml
```

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, Pandas, NumPy, Pydantic
- **Data**: dukascopy-python / equivalent for historical; Twelve Data / FCS / broker for live (keys required)
- **Frontend**: Next.js + TypeScript + Tailwind CSS + Lightweight Charts
- **Database**: PostgreSQL (recommended) or SQLite for local MVP
- **Mobile**: Fully responsive PWA; Capacitor recommended for native Android APK

## Quick Start (Local MVP)

```bash
git clone https://github.com/dilshadahmednisar123/ICT-Institutional-AI-Trading-Scanner.git
cd ICT-Institutional-AI-Trading-Scanner

# Backend
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

## Data Sources — Critical Notes

- **Historical candles**: Free via Dukascopy open data feeds (no key needed for historical).
- **Live / near-real-time**: Requires a paid or free-tier API key (Twelve Data, FCS API, etc.). Rate limits apply.
- The system **never fabricates** candles or prices. Missing or stale data → clear `DATA UNAVAILABLE` status. No signals issued from bad data.

## Core Philosophy (from the master prompt)

1. Identify where liquidity is resting  
2. Wait for a raid + displacement + Market Structure Shift  
3. Identify a valid PD array (FVG / Order Block / Breaker / etc.)  
4. Calculate precise structural entry  
5. Place stop beyond structural invalidation  
6. Target the next meaningful opposing liquidity  
7. Enforce minimum Risk:Reward  
8. Require high confluence  
9. **NO VALID SETUP = NO TRADE**

## License & Disclaimer

MIT License — intended for educational and research purposes.

**Trading involves substantial risk of loss. This software is not financial advice. Past performance is not indicative of future results. Use at your own risk.**

---

Scaffolded according to the complete "ICT INSTITUTIONAL AI TRADING SCANNER" master prompt.
