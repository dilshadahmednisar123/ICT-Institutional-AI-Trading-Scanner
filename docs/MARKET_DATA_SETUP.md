# LIQUIDITY NEXUS market-data setup

## Required symbols and provider entitlements

The production adapter uses Twelve Data only. It requests these exact identifiers:

| LIQUIDITY NEXUS symbol | Twelve Data symbol | Dataset |
|---|---|---|
| EURUSD | `EUR/USD` | Forex |
| XAUUSD | `XAU/USD` | Gold Spot commodity aggregate |

Do not map XAUUSD to `GC=F`, GC futures, or another futures contract.

Twelve Data currently lists real-time forex market data on its Basic individual plan. Its individual pricing page lists commodity market data on Grow and above; its Commodity exchange specification lists the XAU/USD aggregate as real-time, with intraday history from 2020-01-09 at 1-minute through 8-hour intervals and daily history from 1980-01-01. Therefore, for a single individual account that needs both EUR/USD and XAU/USD spot, use **Grow or higher** as the minimum published plan tier. Verify XAU/USD access in the account's symbol/market access page before relying on it; trial/global-symbol access and endpoint responses can differ by account.

Official references:
- https://twelvedata.com/pricing
- https://twelvedata.com/exchanges/COMMODITY
- https://twelvedata.com/markets/300755/commodity/xau-usd
- https://twelvedata.com/docs

The individual Grow tier is listed at USD 79/month on the current pricing page and includes internal display data access. If this app will display data to external customers or be used commercially, confirm the correct commercial licence with Twelve Data; do not assume an individual plan grants external redistribution rights.

## Configure the API key in both environments

The same Twelve Data API key must be added separately to:

1. **Vercel backend production environment** — runtime market scans and API endpoints.
2. **GitHub Actions repository secrets** — CI historical backtests.

### Vercel

Open https://vercel.com/dashboard, select project **liquidity-nexus-api**, then **Settings → Environment Variables**.

Create:
- Name: `TWELVE_DATA_API_KEY`
- Value: your Twelve Data API key
- Environments: Production, Preview, Development (at minimum, Production)

Save. The final manual workflow dispatch redeploys the backend using the Vercel CLI; configure the required `VERCEL_TOKEN` as described in [Vercel CLI Deployment](VERCEL_CLI_DEPLOYMENT.md). If you redeploy manually instead, select the latest `main` commit, not the older production deployment revision.

### GitHub Actions

Open https://github.com/dilshadahmednisar123/ICT-Institutional-AI-Trading-Scanner/settings/secrets/actions

Choose **New repository secret**:
- Name: `TWELVE_DATA_API_KEY`
- Secret: the same Twelve Data API key

Do not paste the key into a commit, issue, workflow file, screenshot, or chat.

## Endpoint smoke tests

After configuration, the backend must successfully request:
- `/time_series?symbol=EUR/USD&interval=15min&outputsize=...`
- `/time_series?symbol=XAU/USD&interval=15min&outputsize=...`
- `/price?symbol=EUR/USD` and `/price?symbol=XAU/USD`

The application converts these to the internal symbols EURUSD and XAUUSD. It must verify returned metadata/symbol identity, non-empty OHLC values, UTC candle alignment, closed-candle status, duplicates/gaps, and freshness. A successful HTTP response alone is not sufficient. A missing entitlement, rate limit, stale series, or symbol mismatch must produce DATA UNAVAILABLE / NO_SETUP, never a substitute instrument or fabricated candles.

## Scan and backtest workload

The scheduled scan currently requests six instruments every 20 minutes. That is approximately 432 one-symbol time-series requests per 24-hour day, before manual scans and backtest requests. Check the account's per-minute credits, daily quota, and plan limits against the full workload. Grow lists 55+ API credits/minute and no daily request cap on the pricing page; the selected quota in the account may vary.

## Legitimate historical-data alternative

Dukascopy publishes downloadable bid/ask historical data for Forex and metals, including XAU/USD spot, with 1-minute and higher-timeframe OHLC data. It is a valid candidate for **offline historical backtesting only** after the project implements and validates a real adapter/import path. The repository's current `DukascopyHistoricalProvider` is only a stub and returns DATA UNAVAILABLE. Do not describe Dukascopy as an active production feed until the adapter is implemented and verified. Do not use it as a live-feed fallback without an appropriate supported service and licence.

References:
- https://www.dukascopy.com/swiss/english/marketwatch/historical/
- https://www.dukascopy-node.app/instrument/xauusd
