# Production deployment and operations

## Live architecture

- **Frontend:** Next.js static export on Vercel.
- **Backend:** FastAPI Python function on Vercel.
- **History:** private Vercel Blob store. Each scan writes an immutable JSON snapshot under `signals/`; the history endpoint lists and reads those snapshots.
- **Automation:** GitHub Actions cron on the repository default branch (`main`) every 20 minutes. It calls the production scan endpoint, checks that persistence succeeded, and reads history back. Vercel's in-process APScheduler is not the production cron mechanism.
- **Data:** production analysis uses authenticated Twelve Data only. Set `TWELVE_DATA_API_KEY` as an encrypted Vercel Production environment variable; also set the same key as a GitHub Actions repository secret if you want the CI historical backtest to run. Without it the API returns DATA UNAVAILABLE and produces no setups. Yahoo Finance is disabled as a trading feed because Yahoo says its Finance data must not be redistributed and is not intended for trading/investing. Synthetic candles are never a production fallback.
- **Gold feed identity:** Twelve Data's XAU/USD instrument is labelled as a spot reference (not broker-specific) and requires a plan with commodity-data entitlement. No GC=F futures proxy is substituted for spot XAUUSD. A broker-specific price feed is still required for execution-quality matching.
- **Feed quality:** candle timestamps are UTC; validation checks OHLC integrity, timeframe alignment, duplicates, intraday missing bars, feed age and weekend closure. Forming candles are excluded before analysis; complete lower-timeframe bars are resampled into UTC-aligned higher-timeframe bars where enough complete source bars exist. Stale, invalid, misaligned or market-closed feeds block setup generation. The feed provider and last closed candle timestamp are returned in each OHLC quality report.
- **Freshness caveat:** Twelve Data requires a user API key; its Basic plan lists real-time forex, while commodities are listed on a higher plan. The XAU/USD symbol is only usable when the account has the required commodity entitlement. Dukascopy has an official historical-data service through its JForex SDK, but the current adapter deliberately returns DATA UNAVAILABLE until a real authenticated connector and suitable worker infrastructure are configured. Treat the scanner as analysis-only and verify broker quotes before any trade.

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
- `TWELVE_DATA_API_KEY`: required for live market data; without it, the API returns DATA UNAVAILABLE and no setups.
- Do not set `ENABLE_SCHEDULER=true` on the Vercel serverless backend as a substitute for a durable cron. Use GitHub Actions for scheduled scans.

## Market-data notes

- Yahoo Finance is disabled in the trading and backtest provider path; no futures proxy is substituted for spot XAUUSD.
- Twelve Data must return authenticated XAU/USD spot candles under a plan with commodity entitlement; otherwise XAUUSD is unavailable.
- The data-quality validator checks OHLC integrity, UTC timeframe alignment, duplicates, intraday gaps, closed-bar status, staleness and weekend closure.
- Stale, unavailable or market-closed data causes the ICT pipeline to return `NO_SETUP`; it never synthesizes prices or trading signals.

## Scan schedule

The workflow `.github/workflows/ci-android.yml` has a `*/20 * * * *` schedule. GitHub scheduled workflows execute from the repository's default branch. The scheduled job is restricted to `refs/heads/main`, first verifies that the deployed backend commit matches the workflow's main-branch commit, then posts a six-symbol 15-minute scan, verifies `persistence.stored=true`, and reads persisted scan history afterward. It retries a failed scan/persistence attempt up to three times. A stale deployment is rejected before scanning.

Manual workflow dispatch also runs the production scan verification job. Pushes to `main` run backend validation and production acceptance but do not trigger an extra scheduled scan. Android release builds run only for a manual dispatch or a version tag.

## Android release signing

See [ANDROID_RELEASE_SIGNING.md](ANDROID_RELEASE_SIGNING.md). The release workflow requires a persistent keystore and four encrypted repository secrets. It intentionally refuses to publish an APK signed with a throwaway key, because that would break update signing continuity.

## Safety and limitations

- Mode remains **SIGNAL_ONLY**. This application does not place trades.
- Liquidity pools, structure events, model confluence and setup scores are deterministic heuristics; they are not proof of institutional positioning or calibrated probabilities.
- Do not trade from stale or unavailable market data.
- Never commit API keys, Blob tokens, keystores or signing passwords.
