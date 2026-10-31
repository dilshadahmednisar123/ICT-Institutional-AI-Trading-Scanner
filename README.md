# ICT Institutional AI Trading Scanner

**Signal-only ICT scanner for Forex & Gold.**  
**NO TRADE** when conditions fail.

**Repo:** https://github.com/dilshadahmednisar123/ICT-Institutional-AI-Trading-Scanner  
**Version:** `0.9.0-auth-redis-backtest`

## Stack status

| Area | Status |
|------|--------|
| 7 ICT models + SMT | ✅ |
| Structure / FVG / Liquidity / OB / Entry-SL-TP | ✅ |
| Sessions + news filter interface | ✅ |
| Twelve Data live (optional key) | ✅ |
| 20-min scheduler + **Redis job store** (optional) | ✅ |
| **Walk-forward backtest** | ✅ |
| **API key auth** (`API_SECRET_KEY`) | ✅ |
| Chart overlays (Entry/SL/TP/EQ) | ✅ |
| Docker Compose (backend + Redis) | ✅ |
| Android Capacitor path | ✅ |
| Production guide | ✅ `docs/PRODUCTION.md` |

## Quick Start

```bash
# Optional
export TWELVE_DATA_API_KEY=...
# export API_SECRET_KEY=...
# export REDIS_URL=redis://localhost:6379/0

cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

cd frontend && npm install && npm run dev
```

Docker: `docker compose up -d`

- UI http://localhost:3000  
- API http://localhost:8000/docs  
- Backtest `GET /api/v1/backtest/EURUSD?limit=400&step=20`

If `API_SECRET_KEY` is set, send header `X-API-Key: <secret>`.

## Philosophy

Liquidity → Raid → Displacement → Structure → PD array → Structural entry → Invalidation stop → Liquidity TP  
**NO VALID SETUP = NO TRADE**

## Docs

- [Production](docs/PRODUCTION.md)  
- [Android APK](docs/ANDROID_APK.md)

## Disclaimer

MIT · Educational · Not financial advice · Trading involves substantial risk of loss.
