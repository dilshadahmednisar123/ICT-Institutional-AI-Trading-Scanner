# Production deployment and operations

## Live architecture

- **Frontend:** Next.js static export on Vercel.
- **Backend:** FastAPI Python function on Vercel.
- **History:** private Vercel Blob store. Each scan writes an immutable JSON snapshot under `signals/`; the history endpoint lists and reads those snapshots.
- **Automation:** GitHub Actions cron on the repository default branch (`main`) every 20 minutes. It calls the production scan endpoint, checks that persistence succeeded, and reads history back. Vercel's in-process APScheduler is not the production cron mechanism.
- **Data:** Yahoo Finance public chart adapter by default; Twelve Data is optional when its key is configured. Synthetic candles are not used for production auto scans.

## Production URLs

- Website: https://liquidity-nexus-agus-902e.vercel.app
- API: https://liquidity-nexus-api-agus-902e.vercel.app
- Health: https://liquidity-nexus-api-agus-902e.vercel.app/health
- Storage health: https://liquidity-nexus-api-agus-902e.vercel.app/api/v1/storage/health
- History: https://liquidity-nexus-api-agus-902e.vercel.app/api/v1/signals

## Required environment

### Frontend Vercel project
```bash
NEXT_PUBLIC_API_URL=https://liquidity-nexus-api-agus-902e.vercel.app
```

### Backend Vercel project
- `BLOB_READ_WRITE_TOKEN`: supplied by the connected private Vercel Blob store.
- `TWELVE_DATA_API_KEY`: optional; when absent, the auto provider uses Yahoo Finance.
- Do not set `ENABLE_SCHEDULER=true` on the Vercel serverless backend as a substitute for a durable cron. Use GitHub Actions for scheduled scans.

## Market-data notes

- Yahoo Finance is the default public feed. Availability and intraday update cadence are not guaranteed.
- `XAUUSD` maps to `GC=F` (gold futures). This is a proxy and may differ from broker spot pricing.
- The data-quality validator checks required OHLC fields, duplicates, gaps and staleness.
- Stale data causes the ICT pipeline to return `NO_SETUP`; it does not synthesize prices or trading signals.

## Scan schedule

The workflow `.github/workflows/ci-android.yml` has a `*/20 * * * *` schedule. GitHub scheduled workflows execute from the repository's default branch. The scheduled job is restricted to `refs/heads/main`, posts a six-symbol 15-minute scan, verifies `persistence.stored=true`, and reads persisted scan history afterward.

Pushes to `main` and manual workflow dispatches also execute the same production scan verification job. This allows a production smoke run without waiting for the next cron tick.

## Android release signing

See [ANDROID_RELEASE_SIGNING.md](ANDROID_RELEASE_SIGNING.md). The release workflow requires a persistent keystore and four encrypted repository secrets. It intentionally refuses to publish an APK signed with a throwaway key, because that would break update signing continuity.

## Safety and limitations

- Mode remains **SIGNAL_ONLY**. This application does not place trades.
- Liquidity pools, structure events, model confluence and setup scores are deterministic heuristics; they are not proof of institutional positioning or calibrated probabilities.
- Do not trade from stale or unavailable market data.
- Never commit API keys, Blob tokens, keystores or signing passwords.
