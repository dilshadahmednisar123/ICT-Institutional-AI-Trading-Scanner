# LIQUIDITY NEXUS
**Decode Liquidity. Follow Smart Money.**

Signal-only institutional ICT scanner for Forex and Gold. **NO VALID SETUP = NO TRADE**.

## Architecture
- Frontend: Next.js 14, React, Tailwind, Lightweight Charts; static export compatible with Capacitor.
- Backend: FastAPI with deterministic ICT analysis engines.
- Scheduler: APScheduler server-side, default 20-minute interval; optional Redis job store.
- Market data: Twelve Data when `TWELVE_DATA_API_KEY` is configured; provider validation and fallback behavior are implemented.
- Android: Capacitor wrapper; GitHub Actions builds an installable debug APK artifact.
- Hosting: Vercel frontend; Render persistent backend blueprint (`render.yaml`).

## ICT modules
Structure/MSS, liquidity pools and sweeps, displacement, FVG, order blocks, premium/discount, entry-risk, scoring, sessions, news-risk filter, SMT, ICT 2022, Silver Bullet, Unicorn, Turtle Soup, OTE, Judas Swing, Power of Three, and walk-forward backtesting.

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

## Deployment
- Frontend: import repository into Vercel, set root directory to `frontend`, configure `NEXT_PUBLIC_API_URL` to the public API URL.
- Backend: create a Render Blueprint from `render.yaml`; set `TWELVE_DATA_API_KEY` in Render secrets.
- Scheduler: configure `ENABLE_SCHEDULER=true`; scheduler runs server-side independently of browser and Android app lifecycle.
- Mobile: push to `main` to run CI and build an installable debug APK. Download it from Actions → workflow run → Artifacts. Tag a commit `v1.0.0` to attach APK to a GitHub Release.

## Operational limitations
The ICT engines are deterministic heuristics, not proof of institutional order flow or guaranteed predictive edge. Live data depends on provider coverage, API credentials and rate limits. The current `/api/v1/signals` endpoint is a placeholder and is not backed by a durable signal-history repository; PostgreSQL provisioning alone does not implement signal persistence. The app is signal-only and does not execute trades. Never commit secrets.
