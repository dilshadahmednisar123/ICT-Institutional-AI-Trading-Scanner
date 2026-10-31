# Production Deployment Guide

## Architecture

- **Backend**: FastAPI + APScheduler on a persistent host (VPS, Railway, Render, Fly.io, etc.)
- **Frontend**: Next.js (Vercel or static export + Capacitor for Android)
- **Optional Redis**: job store for scheduler durability across restarts
- **Data**: set `TWELVE_DATA_API_KEY` for live OHLC (rate limits apply)

## Environment variables

```bash
TWELVE_DATA_API_KEY=          # optional live data
API_SECRET_KEY=               # optional; if set, require X-API-Key header
REDIS_URL=redis://redis:6379/0  # optional scheduler job store
SCAN_INTERVAL_MINUTES=20
DATABASE_URL=                 # future signal persistence
```

## Auth

When `API_SECRET_KEY` is set, protected routes expect:

```
X-API-Key: <your-secret>
```

Leave unset for local development.

## Docker

```bash
export TWELVE_DATA_API_KEY=...
export API_SECRET_KEY=...
docker compose up -d
```

Enable Redis service in `docker-compose.yml` if you need a durable job store.

## Scheduler

```
POST /api/v1/scheduler/start
{"interval_minutes": 20}
```

Runs on the **server**, not in the browser or APK. Mobile clients only display signals.

## HTTPS

Terminate TLS at a reverse proxy (Caddy, Nginx, Cloudflare) in front of the API and frontend.

## Android

See `docs/ANDROID_APK.md`. Point `NEXT_PUBLIC_API_URL` at your public HTTPS API.

## Safety

- Mode remains **SIGNAL_ONLY**
- Never place real trades from this codebase without a separate, audited execution layer
- Never commit API keys
