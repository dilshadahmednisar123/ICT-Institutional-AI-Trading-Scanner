"use client";

import { useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Props = {
  symbol?: string;
  timeframe?: string;
};

export default function PriceChart({ symbol = "EURUSD", timeframe = "15M" }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let chart: any;
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        // Dynamic import so SSR does not break
        const lc = await import("lightweight-charts");
        if (!containerRef.current || cancelled) return;

        containerRef.current.innerHTML = "";
        chart = lc.createChart(containerRef.current, {
          layout: {
            background: { color: "#12181f" },
            textColor: "#94a3b8",
          },
          grid: {
            vertLines: { color: "#1e2a36" },
            horzLines: { color: "#1e2a36" },
          },
          width: containerRef.current.clientWidth,
          height: 360,
          timeScale: { borderColor: "#1e2a36" },
          rightPriceScale: { borderColor: "#1e2a36" },
        });

        const series = chart.addCandlestickSeries({
          upColor: "#22c55e",
          downColor: "#ef4444",
          borderVisible: false,
          wickUpColor: "#22c55e",
          wickDownColor: "#ef4444",
        });

        const res = await fetch(
          `${API_BASE}/api/v1/ohlc/${symbol}?timeframe=${timeframe}&limit=200`
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const candles = (data.candles || []).map((c: any) => ({
          time: c.time as number,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }));
        series.setData(candles);
        chart.timeScale().fitContent();

        const onResize = () => {
          if (containerRef.current && chart) {
            chart.applyOptions({ width: containerRef.current.clientWidth });
          }
        };
        window.addEventListener("resize", onResize);
        return () => window.removeEventListener("resize", onResize);
      } catch (e: any) {
        if (!cancelled) setError(e.message || "Chart load failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
      if (chart) chart.remove();
    };
  }, [symbol, timeframe]);

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <div className="font-medium">{symbol} · {timeframe}</div>
        {loading && <div className="text-xs text-institutional-muted">Loading chart…</div>}
      </div>
      {error && <div className="text-sm text-red-400 mb-2">{error}</div>}
      <div ref={containerRef} className="w-full rounded-lg overflow-hidden" />
      <div className="text-xs text-institutional-muted mt-2">
        Data from API OHLC endpoint. Overlays (FVG/OB/levels) can be added next.
      </div>
    </div>
  );
}
