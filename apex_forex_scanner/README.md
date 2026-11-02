# Apex Forex Scanner

A FastAPI dashboard that scans 28 Yahoo Finance FX symbols on demand.

## Deploy on Vercel
Vercel detects the FastAPI app exported as `app` from `main.py`. The dashboard is served at `/`, health check at `/api/health`, and a fresh market scan at `/api/scan`.

## Runtime model
Vercel Functions are ephemeral. This version intentionally does not start an endless background task or rely on process memory surviving between requests. A scan runs when `/api/scan` is requested; the dashboard requests one immediately on button click and repeats every 20 minutes while the page remains open.

The Vercel team currently connected to this project is on the Hobby plan. Vercel Hobby Cron Jobs are limited to once per day, so a true unattended 20-minute server-side scan cannot be scheduled on that plan. A paid Vercel plan or an external scheduler/worker is required for 20-minute scans when the dashboard is closed.

## Run locally
```bash
python -m venv .venv
# Activate the environment
pip install -r requirements.txt
uvicorn main:app --reload
```
Open http://127.0.0.1:8000.

## Trading limitations
This is a basic EMA trend and swing-level ranking prototype, not a complete ICT/SMC engine. It does not validate BOS/CHOCH, order blocks, FVG, liquidity sweeps, broker spread, or an economic calendar. Yahoo Finance can return delayed or incomplete quotes. Pip conversion handles JPY quote pairs separately, but the stop is a percentage approximation, not an ATR- or broker-calibrated stop. No orders are sent. Treat output as research only and independently validate all prices and risk.
