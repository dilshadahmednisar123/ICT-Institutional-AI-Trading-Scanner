# LIQUIDITY NEXUS
**Decode Liquidity. Follow Smart Money.**

Signal-only ICT scanner for Forex and Gold. **NO VALID SETUP = NO TRADE**.

## Production
- **Website:** https://liquidity-nexus-agus-902e.vercel.app
- **API:** https://liquidity-nexus-api-agus-902e.vercel.app
- **API health:** https://liquidity-nexus-api-agus-902e.vercel.app/health
- **Repository:** https://github.com/dilshadahmednisar123/ICT-Institutional-AI-Trading-Scanner

## Architecture
- Frontend: Next.js 14, React, Tailwind, Lightweight Charts; static export compatible with Capacitor.
- Backend: FastAPI deployed as a Vercel Python function.
- History: private Vercel Blob snapshots; scans are written as immutable JSON objects and read back by the history endpoint.
- Automation: GitHub Actions scheduled workflow on `main`, every 20 minutes, invokes production scan and verifies persistence. The in-process APScheduler is not relied on for Vercel serverless scheduling.
- Market data: authenticated Twelve Data only. Configure `TWELVE_DATA_API_KEY` in both Vercel backend Environment Variables and GitHub Actions repository secrets; without it the API returns DATA UNAVAILABLE and no setups. See [Market Data Setup](docs/MARKET_DATA_SETUP.md). Yahoo Finance is disabled for trading use; synthetic candles are test-only.
- Gold: XAU/USD is accepted only from a Twelve Data account with the required commodity-data entitlement. No GC=F futures proxy is substituted for spot XAUUSD. The current Dukascopy adapter is a stub, not an active fallback.
- Candle validation: closed bars only, UTC timeframe alignment, duplicate/gap detection, stale-feed blocking, and complete lower-to-higher timeframe resampling.
- Android: Capacitor wrapper. The release workflow requires a persistent Android signing keystore configured as GitHub Actions secrets; see `docs/ANDROID_RELEASE_SIGNING.md`.

## ICT modules
Market structure and close-confirmed BOS/CHOCH, liquidity pools and sweeps, displacement, FVG, order blocks, premium/discount, structural entry and stop, opposing-liquidity take-profit selection, RR calculation, confluence scoring, sessions, news-risk filter, SMT, ICT 2022, Silver Bullet, Unicorn, Turtle Soup, OTE, Judas Swing, Power of Three, and walk-forward backtesting.

## Local development
```bash
cd backend
python -m venv .venv
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
In another terminal:
```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

## Deployment configuration
- Frontend Vercel root: `frontend`; set `NEXT_PUBLIC_API_URL` to the production API.
- Backend Vercel root: `backend`; connect the private Blob store so `BLOB_READ_WRITE_TOKEN` is available.
- GitHub schedule: `.github/workflows/ci-android.yml` uses `*/20 * * * *` on the repository default branch (`main`).
- Android signing: configure the four secrets documented in `docs/ANDROID_RELEASE_SIGNING.md`. Do not commit a keystore or passwords.

## Operational limitations
- The ICT engines are deterministic heuristics, not proof of institutional order flow or a guaranteed predictive edge.
- Setup scores are confluence scores, not calibrated win probabilities.
- Market-data freshness is validated; stale or unavailable candles result in NO_SETUP rather than a fabricated trade.
- The product is signal-only and does not execute trades.
- Never commit API keys, Blob tokens, or Android signing material.
