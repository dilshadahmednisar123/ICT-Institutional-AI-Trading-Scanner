# LIQUIDITY NEXUS MCP

Read-only Model Context Protocol server for Forex and XAUUSD.

## Data source

The first implementation uses biquote's public MT5 broker-feed API. Its documentation states that read endpoints are keyless, includes EURUSD/XAUUSD, offers OHLC intervals from 1m to 1d, and identifies its source as MT5. This is a broker/CFD feed, not a consolidated market tape. FX/CFD volume is not real traded volume; the ICT tool does not use it as volume confirmation.

The provider reports market state and quote age. Open candles are excluded. Stale or missing candles produce DATA_UNAVAILABLE/STALE and never synthetic data.

## Tools

- market_data_status
- get_market_quote
- get_ohlc_candles
- scan_ict_smc
- get_high_impact_calendar
- list_supported_instruments

The ICT scan is a transparent candle-based heuristic. It is not proof of institutional order flow, does not produce calibrated win probabilities, and never places trades.

## Local Windows run

Requires Python 3.11+.

```powershell
cd mcp_service
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python server.py
```

The local MCP endpoint is http://localhost:8000/mcp.

## Vercel

Create a Vercel project linked to this repository with Root Directory set to `mcp_service`. The configured MCP endpoint is `/api/index`. Verify the deployed endpoint using an MCP client and list_tools before adding it to ChatGPT. This service is stateless and read-only.

No API keys are required for the documented public read endpoints. Free-tier hosting quotas and provider terms can change; verify before production use.
