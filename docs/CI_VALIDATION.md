# LIQUIDITY NEXUS CI validation

- Backend: Python compile check, dependency installation, FastAPI health and instruments smoke tests.
- Android: Next.js static export, Capacitor Android sync, Gradle debug APK, signature/alignment verification, artifact upload.
- Android production API origin: https://liquidity-nexus-api-agus-902e.vercel.app
- Scheduled live scans: GitHub Actions every 20 minutes; scan snapshots retained as workflow artifacts.
- Persistent scan history: private Vercel Blob store through its REST API; no synthetic candles in live mode.
- Live feeds: Twelve Data when configured, otherwise Yahoo Finance. XAUUSD uses a clearly labelled GC=F futures proxy.
- Stale candles are rejected and cannot produce trade signals.
- Setup scores are heuristic confluence scores, not calibrated win probabilities.
