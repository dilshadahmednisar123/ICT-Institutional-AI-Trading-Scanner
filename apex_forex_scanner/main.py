from pathlib import Path
import asyncio
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from engine import scan_market

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("apex.api")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app = FastAPI(title="Apex Forex Scanner", version="1.0.0")

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/health")
async def health():
    return {"ok": True, "service": "Apex Forex Scanner", "mode": "serverless on-demand scan"}

@app.get("/api/scan")
async def get_scan():
    # Vercel functions are ephemeral: do not depend on a background asyncio task
    # or process-local cache surviving between requests. Each call performs a
    # fresh scan and returns its own timestamp.
    try:
        result = await asyncio.wait_for(scan_market(), timeout=270)
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Market scan exceeded the 270-second execution budget. Try again later.")
    except Exception as exc:
        log.exception("Market scan failed")
        raise HTTPException(status_code=502, detail=f"Market data scan failed: {type(exc).__name__}")
