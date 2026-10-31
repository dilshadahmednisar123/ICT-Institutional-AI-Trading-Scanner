# ICT Institutional AI Trading Scanner

**Production-oriented AI-powered ICT (Inner Circle Trader) Institutional Trading Scanner for Forex & Gold.**

> Signal-only mode by default. Highly selective. **NO TRADE** is a valid and preferred outcome when conditions are not met.

**Repository:** https://github.com/dilshadahmednisar123/ICT-Institutional-AI-Trading-Scanner

## Current Progress (v0.2.0-core-engines)

### Fully Implemented & Wired

| Module | Status | Notes |
|--------|--------|-------|
| Data Provider Layer | ✅ | Abstract provider + quality checks + Dukascopy placeholder + Synthetic for offline |
| Swing High/Low | ✅ | Configurable left/right, non-repainting |
| Market Structure | ✅ | HH/HL/LH/LL + BOS detection |
| Fair Value Gaps | ✅ | Bullish/Bearish FVG + CE + mitigation tracking |
| Liquidity Engine | ✅ | BSL/SSL, Equal Highs/Lows, Sweep detection + ranking |
| Displacement | ✅ | Body/Range + ATR-normalized quality score |
| Premium/Discount | ✅ | Dealing range + 0/25/50/62/70.5/79/100 levels |
| Core Analysis Pipeline | ✅ | Full sequential pass producing structured results |
| FastAPI Backend | ✅ | `/api/v1/scan`, `/api/v1/analyze/{symbol}`, health, instruments |

### Still Pending for Full Production

- Complete state machines for all 16 ICT trading models
- Real live data feed (requires your API keys)
- Persistent 20-minute scheduler (Celery/Redis)
- Structural Entry / SL / Liquidity TP calculation (framework exists, needs model integration)
- 100-point confluence scoring engine
- Order Block / Breaker / Mitigation full detectors
- News calendar filter
- SMT Divergence
- Backtesting engine
- Frontend dashboard + charts
- Android APK / Capacitor packaging
- Auth + production deployment

## Quick Start

```bash
git clone https://github.com/dilshadahmednisar123/ICT-Institutional-AI-Trading-Scanner.git
cd ICT-Institutional-AI-Trading-Scanner/backend

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run the API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then open:
- http://localhost:8000/docs  (interactive Swagger UI)
- POST `/api/v1/scan` with body `{"symbols": ["EURUSD", "XAUUSD"], "timeframe": "15M"}`
- GET `/api/v1/analyze/EURUSD?timeframe=15M`

## Philosophy (enforced in code)

1. Liquidity first  
2. Wait for raid + displacement + structure shift  
3. Valid PD array  
4. Precise structural entry  
5. Stop beyond invalidation  
6. Target next meaningful opposing liquidity  
7. Minimum RR filter  
8. High confluence required  
9. **NO VALID SETUP = NO TRADE**

## Data Notes

- Historical data path is prepared for free Dukascopy libraries.
- Current runtime uses a controlled synthetic fallback so the pipeline can be developed and tested offline without external keys.
- The system **never invents** real market prices for live trading decisions. When real data is unavailable it returns clear `DATA UNAVAILABLE` / quality flags.

## License & Disclaimer

MIT License — educational and research use.

**Trading involves substantial risk of loss. This is not financial advice.**
