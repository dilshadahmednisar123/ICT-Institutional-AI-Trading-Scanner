"use client";

import { useEffect, useId, useState } from "react";

type Props = {
  symbol?: string;
  timeframe?: string;
};

const SYMBOLS: Record<string, string> = {
  EURUSD: "FX:EURUSD",
  GBPUSD: "FX:GBPUSD",
  USDJPY: "FX:USDJPY",
  USDCHF: "FX:USDCHF",
  AUDUSD: "FX:AUDUSD",
  USDCAD: "FX:USDCAD",
  NZDUSD: "FX:NZDUSD",
  EURJPY: "FX:EURJPY",
  GBPJPY: "FX:GBPJPY",
  XAUUSD: "OANDA:XAUUSD",
};

const TIMEFRAMES: Record<string, string> = {
  "1M": "1",
  "5M": "5",
  "15M": "15",
  "30M": "30",
  "1H": "60",
  "4H": "240",
  "1D": "D",
};

declare global {
  interface Window {
    TradingView?: { widget: new (config: Record<string, unknown>) => { remove?: () => void; onChartReady?: (callback: () => void) => void } };
  }
}

export default function PriceChart({ symbol = "EURUSD", timeframe = "15M" }: Props) {
  const generatedId = useId().replace(/:/g, "");
  const containerId = `tv_chart_${generatedId}`;
  const [activeSymbol, setActiveSymbol] = useState(symbol);
  const [activeTimeframe, setActiveTimeframe] = useState(timeframe);
  const [retry, setRetry] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setActiveSymbol(symbol), [symbol]);
  useEffect(() => setActiveTimeframe(timeframe), [timeframe]);

  useEffect(() => {
    let disposed = false;
    let widget: { remove?: () => void } | undefined;
    let timeout: ReturnType<typeof setTimeout> | undefined;

    const mountWidget = () => {
      if (disposed) return;
      const host = document.getElementById(containerId);
      if (!host) return;
      if (!window.TradingView?.widget) {
        setError("TradingView did not initialize. Check your connection and retry.");
        setLoading(false);
        return;
      }
      try {
        host.innerHTML = "";
        widget = new window.TradingView.widget({
          autosize: true,
          symbol: SYMBOLS[activeSymbol] || `FX:${activeSymbol}`,
          interval: TIMEFRAMES[activeTimeframe] || "15",
          timezone: "Etc/UTC",
          theme: "dark",
          style: "1",
          locale: "en",
          toolbar_bg: "#0b1420",
          enable_publishing: false,
          allow_symbol_change: true,
          save_image: false,
          hide_side_toolbar: false,
          withdateranges: true,
          details: true,
          hotlist: false,
          calendar: false,
          studies: [],
          support_host: "https://www.tradingview.com",
          container_id: containerId,
        });
        if (widget?.onChartReady) {
          widget.onChartReady(() => {
            if (!disposed) {
              setLoading(false);
              setError(null);
            }
          });
        } else {
          setLoading(false);
        }
      } catch (e) {
        if (!disposed) {
          setError(e instanceof Error ? e.message : "TradingView chart initialization failed.");
          setLoading(false);
        }
      }
    };

    setLoading(true);
    setError(null);
    const existing = document.querySelector<HTMLScriptElement>('script[data-tradingview-widget="true"]');
    if (window.TradingView?.widget) {
      mountWidget();
    } else if (existing) {
      existing.addEventListener("load", mountWidget, { once: true });
      existing.addEventListener("error", () => {
        if (!disposed) {
          setError("Unable to load TradingView. Check network restrictions and retry.");
          setLoading(false);
        }
      }, { once: true });
    } else {
      const script = document.createElement("script");
      script.src = "https://s3.tradingview.com/tv.js";
      script.async = true;
      script.dataset.tradingviewWidget = "true";
      script.onload = mountWidget;
      script.onerror = () => {
        if (!disposed) {
          setError("TradingView script was blocked or could not be downloaded. Check browser network/CSP settings and retry.");
          setLoading(false);
        }
      };
      document.head.appendChild(script);
    }

    timeout = setTimeout(() => {
      if (!disposed && loading) {
        setError("TradingView is taking too long to load. Check your connection and retry.");
        setLoading(false);
      }
    }, 18000);

    return () => {
      disposed = true;
      if (timeout) clearTimeout(timeout);
      try { widget?.remove?.(); } catch { /* TradingView may already have disposed the iframe. */ }
      const host = document.getElementById(containerId);
      if (host) host.innerHTML = "";
    };
  }, [containerId, activeSymbol, activeTimeframe, retry]);

  return (
    <section className="card">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
        <div>
          <div className="font-semibold tracking-wide">LIVE MARKET CHART</div>
          <div className="text-xs text-institutional-muted mt-1">
            TradingView · {SYMBOLS[activeSymbol] || activeSymbol} · {activeTimeframe}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <label className="sr-only" htmlFor={`symbol-${generatedId}`}>Chart symbol</label>
          <select id={`symbol-${generatedId}`} value={activeSymbol} onChange={(e) => setActiveSymbol(e.target.value)} className="bg-slate-900 border border-institutional-border rounded-lg px-3 py-2 text-sm">
            {Object.keys(SYMBOLS).map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <label className="sr-only" htmlFor={`timeframe-${generatedId}`}>Chart timeframe</label>
          <select id={`timeframe-${generatedId}`} value={activeTimeframe} onChange={(e) => setActiveTimeframe(e.target.value)} className="bg-slate-900 border border-institutional-border rounded-lg px-3 py-2 text-sm">
            {Object.keys(TIMEFRAMES).map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </div>
      </div>
      {loading && <div className="text-xs text-cyan-300 mb-2" role="status">Connecting to TradingView…</div>}
      {error && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-950/20 p-3 mb-3 text-sm text-amber-200">
          <div>{error}</div>
          <button onClick={() => setRetry((n) => n + 1)} className="mt-2 rounded-md border border-amber-400/40 px-3 py-1.5 text-xs font-semibold hover:bg-amber-900/30">
            Retry chart
          </button>
        </div>
      )}
      <div id={containerId} className="w-full overflow-hidden rounded-lg bg-[#0b1420]" style={{ height: "min(560px, 72vh)", minHeight: "390px" }} />
      <p className="text-[11px] text-institutional-muted mt-2">
        Spot FX: FX symbols · Spot gold: OANDA:XAUUSD. TradingView supplies chart data; no futures proxy or generated candles are used.
      </p>
    </section>
  );
}
