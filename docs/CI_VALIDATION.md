# LIQUIDITY NEXUS CI validation

This repository uses GitHub Actions to validate the FastAPI backend and build the Capacitor Android debug APK.

- Backend validation: Python compile check and FastAPI smoke tests.
- Android validation: Next.js static build, Capacitor Android sync, Gradle debug APK.
- Android builds embed the public production API origin: https://liquidity-nexus-api-agus-902e.vercel.app
- Scheduled scans are dispatched by GitHub Actions every 20 minutes. Results are retained as workflow artifacts for 7 days.
- Live market data is sourced from Twelve Data when configured, otherwise Yahoo Finance. Synthetic candles are disabled in live mode.
- Stale market data is explicitly rejected and cannot produce executable signals.

The scanner is signal-only. Confluence scores are heuristic scores, not calibrated win probabilities.
