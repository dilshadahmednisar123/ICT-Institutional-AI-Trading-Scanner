"use client";

import { useEffect, useRef, useState } from "react";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

type Props = {
  symbol?: string;
  timeframe?: string;
  overlays?: {
    trade?: { entry?: number; stop?: number; tp1?: number; tp2?: number; direction?: string };
    dealing_range?: { high?: number; low?: number; eq?: number };
    fvgs?: { upper: number; lower: number; direction: string }[];
  } | null;
};

export default function PriceChart({ symbol = "EURUSD", timeframe = "15M", overlays }: Props) {
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
        if (!API_BASE) throw new Error("Production API is not configured. Set NEXT_PUBLIC_API_URL and redeploy.");
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
          height: 380,
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

        // Overlays: entry / SL / TP / dealing range as price lines
        const addLine = (price: number | undefined, color: string, title: string) => {
          if (price == null || Number.isNaN(price)) return;
          series.createPriceLine({
            price,
            color,
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: true,
            title,
          });
        };

        if (overlays?.trade) {
          addLine(overlays.trade.entry, "#3b82f6", "Entry");
          addLine(overlays.trade.stop, "#ef4444", "SL");
          addLine(overlays.trade.tp1, "#22c55e", "TP1");
          addLine(overlays.trade.tp2, "#16a34a", "TP2");
        }
        if (overlays?.dealing_range) {
          addLine(overlays.dealing_range.high, "#64748b", "Range H");
          addLine(overlays.dealing_range.low, "#64748b", "Range L");
          addLine(overlays.dealing_range.eq, "#a78bfa", "EQ");
        }

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
  }, [symbol, timeframe, overlays]);

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <div className="font-medium">{symbol} · {timeframe}</div>
        {loading && <div className="text-xs text-institutional-muted">Loading chart…</div>}
      </div>
      {error && <div className="text-sm text-red-400 mb-2">{error}</div>}
      <div ref={containerRef} className="w-full rounded-lg overflow-hidden" />
      <div className="text-xs text-institutional-muted mt-2">
        Blue = Entry · Red = SL · Green = TP · Purple = Equilibrium (when setup present)
      </div>
    </div>
  );
}
