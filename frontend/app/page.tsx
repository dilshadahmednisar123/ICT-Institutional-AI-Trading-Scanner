"use client";

import { useMemo, useState } from "react";
import PriceChart from "../components/PriceChart";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

type ScanResult = {
  symbol: string;
  current_price?: number;
  bias?: string;
  premium_discount?: string;
  sessions?: string[];
  in_silver_bullet_window?: boolean;
  news_risk?: string;
  setup_status: string;
  best_setup?: any;
  chart_overlays?: any;
  smt?: any;
  data_quality?: {
    provider?: string;
    last_timestamp?: string;
    stale?: boolean;
    is_valid?: boolean;
    market_status?: string;
    gaps_detected?: number;
    missing_candles?: number;
    duplicate_candles?: number;
    misaligned_candles?: number;
    message?: string;
  };
  notes?: string[];
  error?: string;
};

export default function Dashboard() {
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<ScanResult[]>([]);
  const [meta, setMeta] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState("EURUSD");

  const selectedResult = useMemo(
    () => results.find((r) => r.symbol === selected),
    [results, selected]
  );

  const overlays = useMemo(() => {
    if (selectedResult?.chart_overlays) return selectedResult.chart_overlays;
    if (selectedResult?.best_setup?.levels) {
      const lv = selectedResult.best_setup.levels;
      return {
        trade: {
          entry: lv.entry,
          stop: lv.stop_loss,
          tp1: lv.tp1,
          tp2: lv.tp2,
          direction: selectedResult.best_setup.direction,
        },
        dealing_range: selectedResult.best_setup
          ? undefined
          : undefined,
      };
    }
    return null;
  }, [selectedResult]);

  async function runScan() {
    setLoading(true);
    setError(null);
    try {
      if (!API_BASE) throw new Error("Production API is not configured. Set NEXT_PUBLIC_API_URL and redeploy.");
      const res = await fetch(`${API_BASE}/api/v1/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbols: ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "AUDUSD", "EURJPY"],
          timeframe: "15M",
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setResults(data.results || []);
      setMeta({
        scanned: data.scanned,
        confirmed: data.confirmed,
        developing: data.developing,
        no_setup: data.no_setup,
        message: data.message,
      });
    } catch (e: any) {
      setError(e.message || "Failed to reach the configured production API.");
    } finally {
      setLoading(false);
    }
  }

  function statusBadge(status: string) {
    if (status === "CONFIRMED") return "badge badge-confirmed";
    if (status === "DEVELOPING") return "badge badge-developing";
    return "badge badge-none";
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Market Scanner</h1>
          <p className="text-sm text-institutional-muted mt-1">
            Deterministic ICT analysis · Signal-only · NO TRADE preferred when conditions fail
          </p>
        </div>
        <button
          onClick={runScan}
          disabled={loading}
          className="px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 font-medium text-sm transition"
        >
          {loading ? "Scanning…" : "Run Scan"}
        </button>
      </div>

      {error && (
        <div className="card border-red-500/40 text-red-300 text-sm">{error}</div>
      )}

      {meta && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="card text-center">
            <div className="text-2xl font-semibold">{meta.scanned}</div>
            <div className="text-xs text-institutional-muted">Scanned</div>
          </div>
          <div className="card text-center">
            <div className="text-2xl font-semibold text-green-400">{meta.confirmed}</div>
            <div className="text-xs text-institutional-muted">Confirmed</div>
          </div>
          <div className="card text-center">
            <div className="text-2xl font-semibold text-yellow-400">{meta.developing}</div>
            <div className="text-xs text-institutional-muted">Developing</div>
          </div>
          <div className="card text-center">
            <div className="text-2xl font-semibold text-slate-400">{meta.no_setup}</div>
            <div className="text-xs text-institutional-muted">No Setup</div>
          </div>
        </div>
      )}

      <PriceChart symbol={selected} timeframe="15M" overlays={overlays} />

      {selectedResult?.data_quality && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="card">
            <div className="text-xs text-institutional-muted mb-1">FEED STATUS</div>
            <div className={selectedResult.data_quality.market_status === "market_closed" || selectedResult.data_quality.stale || !selectedResult.data_quality.is_valid ? "text-amber-300 font-semibold" : "text-green-400 font-semibold"}>
              {selectedResult.data_quality.market_status === "market_closed" ? "MARKET CLOSED" : selectedResult.data_quality.stale ? "STALE" : selectedResult.data_quality.is_valid ? "FRESH" : "UNAVAILABLE"}
            </div>
            <div className="text-xs text-institutional-muted mt-1">{selectedResult.data_quality.message || "Feed quality not reported"}</div>
          </div>
          <div className="card">
            <div className="text-xs text-institutional-muted mb-1">DATA PROVIDER</div>
            <div className="text-sm font-medium break-words">{selectedResult.data_quality.provider || "Unknown"}</div>
          </div>
          <div className="card">
            <div className="text-xs text-institutional-muted mb-1">LAST CANDLE (UTC)</div>
            <div className="text-sm font-medium tabular-nums">{selectedResult.data_quality.last_timestamp ? new Date(selectedResult.data_quality.last_timestamp).toLocaleString("en-GB", { timeZone: "UTC", hour12: false }) : "—"}</div>
          </div>
          <div className="card">
            <div className="text-xs text-institutional-muted mb-1">DATA INTEGRITY</div>
            <div className="text-sm font-medium">Gaps {selectedResult.data_quality.gaps_detected ?? 0} · Missing {selectedResult.data_quality.missing_candles ?? 0}</div>
            <div className="text-xs text-institutional-muted mt-1">Duplicates {selectedResult.data_quality.duplicate_candles ?? 0} · Misaligned {selectedResult.data_quality.misaligned_candles ?? 0}</div>
          </div>
        </div>
      )}

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-institutional-muted border-b border-institutional-border">
              <th className="pb-3 pr-4">Symbol</th>
              <th className="pb-3 pr-4">Price</th>
              <th className="pb-3 pr-4">Bias</th>
              <th className="pb-3 pr-4">P/D</th>
              <th className="pb-3 pr-4">Session</th>
              <th className="pb-3 pr-4">SMT</th>
              <th className="pb-3 pr-4">Status</th>
              <th className="pb-3 pr-4">Model / Score</th>
              <th className="pb-3">Notes</th>
            </tr>
          </thead>
          <tbody>
            {results.length === 0 && (
              <tr>
                <td colSpan={9} className="py-10 text-center text-institutional-muted">
                  Click <strong>Run Scan</strong> to analyze markets. Empty results are normal and preferred.
                </td>
              </tr>
            )}
            {results.map((r) => (
              <tr
                key={r.symbol}
                className="border-b border-institutional-border/60 hover:bg-white/[0.02] cursor-pointer"
                onClick={() => setSelected(r.symbol)}
              >
                <td className="py-3 pr-4 font-medium">{r.symbol}</td>
                <td className="py-3 pr-4 tabular-nums">{r.current_price?.toFixed(5) ?? "—"}</td>
                <td className="py-3 pr-4 capitalize">{r.bias ?? "—"}</td>
                <td className="py-3 pr-4 capitalize">{r.premium_discount ?? "—"}</td>
                <td className="py-3 pr-4 text-xs">
                  {(r.sessions || []).join(", ") || "—"}
                  {r.in_silver_bullet_window && <span className="ml-1 text-blue-400">SB</span>}
                </td>
                <td className="py-3 pr-4 text-xs capitalize">
                  {r.smt?.divergence || (r.smt?.available === false ? "n/a" : "—")}
                </td>
                <td className="py-3 pr-4">
                  <span className={statusBadge(r.setup_status)}>{r.setup_status}</span>
                </td>
                <td className="py-3 pr-4 text-xs">
                  {r.best_setup ? (
                    <>
                      <div>{r.best_setup.model}</div>
                      <div className="text-institutional-muted">
                        {r.best_setup.direction} · Score{" "}
                        {r.best_setup.score ?? r.best_setup.score_breakdown?.total ?? "—"}
                      </div>
                    </>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="py-3 text-xs text-institutional-muted max-w-xs truncate">
                  {(r.notes || []).join(" · ") || r.error || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="text-xs text-institutional-muted text-center pt-4">
        Backend: {API_BASE}. Auto feed: Twelve Data preferred when configured, Yahoo Finance fallback. XAUUSD may be a GC=F futures proxy, not spot. Stale or unavailable data never produces trade signals.
      </div>
    </div>
  );
}
