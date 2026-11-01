"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import PriceChart from "../components/PriceChart";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
const WATCHLIST = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "AUDUSD", "USDCAD"];

type ScanResult = {
  symbol: string;
  current_price?: number | null;
  bias?: string;
  premium_discount?: string;
  sessions?: string[];
  in_silver_bullet_window?: boolean;
  setup_status: string;
  best_setup?: any;
  smt?: any;
  data_quality?: {
    provider?: string;
    last_timestamp?: string;
    stale?: boolean;
    is_valid?: boolean;
    market_status?: string;
    message?: string;
  };
  notes?: string[];
  error?: string;
};

type ScanSnapshot = {
  timestamp_utc: string;
  source?: string;
  workflow_run_id?: string | null;
  scanned: number;
  symbols?: string[];
  confirmed: number;
  developing: number;
  no_setup: number;
  data_available: boolean;
};

type ScannerStatus = {
  scheduler: string;
  cron: string;
  timezone: string;
  active: boolean;
  status: "ACTIVE" | "INACTIVE";
  scanning: boolean;
  last_successful_scan_utc: string | null;
  last_scan_utc: string | null;
  next_scan_utc: string | null;
  scanned: number;
  confirmed: number;
  developing: number;
  no_setup: number;
  data_available: boolean;
  active_reason: string;
  latest_results: ScanResult[];
  recent_scans: ScanSnapshot[];
};

function formatTime(value?: string | null) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not recorded";
  return date.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

function countdown(value: string | null, now: number) {
  if (!value) return "Awaiting scheduler data";
  const remaining = Math.max(0, new Date(value).getTime() - now);
  const total = Math.floor(remaining / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return [hours, minutes, seconds].map((n) => String(n).padStart(2, "0")).join(":");
}

export default function Dashboard() {
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<ScanResult[]>([]);
  const [scanner, setScanner] = useState<ScannerStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState("EURUSD");
  const [now, setNow] = useState(Date.now());
  const [statusError, setStatusError] = useState<string | null>(null);

  const refreshStatus = useCallback(async () => {
    if (!API_BASE) {
      setStatusError("Production API is not configured.");
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/api/v1/scanner/status`, { cache: "no-store" });
      if (!response.ok) throw new Error(`Scanner status HTTP ${response.status}`);
      const data: ScannerStatus = await response.json();
      setScanner(data);
      setResults(data.latest_results || []);
      setStatusError(null);
    } catch (e) {
      setStatusError(e instanceof Error ? e.message : "Unable to refresh scanner status.");
    }
  }, []);

  useEffect(() => {
    refreshStatus();
    const poll = window.setInterval(refreshStatus, 30000);
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      window.clearInterval(poll);
      window.clearInterval(clock);
    };
  }, [refreshStatus]);

  const selectedResult = useMemo(
    () => results.find((item) => item.symbol === selected),
    [results, selected]
  );

  async function runScan() {
    setLoading(true);
    setError(null);
    try {
      if (!API_BASE) throw new Error("Production API is not configured.");
      const response = await fetch(`${API_BASE}/api/v1/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Scan-Source": "manual" },
        body: JSON.stringify({ symbols: WATCHLIST, timeframe: "15M" }),
      });
      if (!response.ok) throw new Error(`Scan request failed: HTTP ${response.status}`);
      const data = await response.json();
      if (data.status !== "completed") throw new Error("The scan did not complete successfully.");
      setResults(data.results || []);
      await refreshStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Manual scan failed.");
    } finally {
      setLoading(false);
    }
  }

  const marketStatus = scanner?.data_available ? "LIVE DATA AVAILABLE" : "DATA UNAVAILABLE";
  const lastScan = scanner?.last_successful_scan_utc;

  function statusBadge(status: string) {
    if (status === "CONFIRMED") return "badge badge-confirmed";
    if (status === "DEVELOPING") return "badge badge-developing";
    return "badge badge-none";
  }

  return (
    <div className="space-y-5">
      <section className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <p className="text-xs tracking-[0.22em] text-cyan-300 font-semibold">LIQUIDITY NEXUS / OPERATIONS</p>
          <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight mt-1">Automated Market Scanner</h1>
          <p className="text-sm text-institutional-muted mt-1">Scheduled ICT analysis · Forex and spot gold · Signal-only</p>
        </div>
        <button onClick={runScan} disabled={loading} className="px-5 py-3 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 font-semibold text-sm transition">
          {loading ? "Scan request running…" : "Scan Now"}
        </button>
      </section>

      <section className="card border border-institutional-border">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-xs tracking-[0.18em] text-institutional-muted">AUTOMATED SCANNER</div>
            <div className="flex items-center gap-2 mt-2">
              <span className={scanner?.active ? "inline-block w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" : "inline-block w-2.5 h-2.5 rounded-full bg-amber-400"} />
              <span className={scanner?.active ? "text-emerald-300 font-semibold text-lg" : "text-amber-300 font-semibold text-lg"}>
                {scanner?.status || "CHECKING"}
              </span>
            </div>
            <p className="text-xs text-institutional-muted mt-1">{scanner?.active_reason || "Reading verified scheduler history…"}</p>
          </div>
          <div className="text-left sm:text-right">
            <div className="text-xs text-institutional-muted">NEXT SCHEDULED SCAN · UTC</div>
            <div className="text-2xl sm:text-3xl font-mono tabular-nums mt-1">{countdown(scanner?.next_scan_utc || null, now)}</div>
            <div className="text-xs text-institutional-muted mt-1">{formatTime(scanner?.next_scan_utc)}</div>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-5 pt-4 border-t border-institutional-border">
          <div>
            <div className="text-[11px] text-institutional-muted">LAST SUCCESSFUL SCHEDULED SCAN</div>
            <div className="text-sm font-medium mt-1">{formatTime(lastScan)}</div>
          </div>
          <div>
            <div className="text-[11px] text-institutional-muted">SCHEDULER</div>
            <div className="text-sm font-medium mt-1">{scanner?.scheduler || "GitHub Actions"} · Every 20 minutes</div>
          </div>
          <div>
            <div className="text-[11px] text-institutional-muted">MARKET DATA CONNECTION</div>
            <div className={scanner?.data_available ? "text-sm font-semibold text-emerald-300 mt-1" : "text-sm font-semibold text-amber-300 mt-1"}>{marketStatus}</div>
          </div>
        </div>
      </section>

      {(error || statusError) && <div className="card border border-red-500/40 text-red-300 text-sm">{error || statusError}</div>}

      <section className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="card"><div className="text-xs text-institutional-muted">INSTRUMENTS SCANNED</div><div className="text-2xl font-semibold mt-1 tabular-nums">{scanner?.scanned ?? results.length}/{WATCHLIST.length}</div><div className="text-[11px] text-institutional-muted mt-1">Latest completed run</div></div>
        <div className="card"><div className="text-xs text-institutional-muted">CONFIRMED SETUPS</div><div className="text-2xl font-semibold text-emerald-300 mt-1 tabular-nums">{scanner?.confirmed ?? 0}</div><div className="text-[11px] text-institutional-muted mt-1">Valid confirmed conditions</div></div>
        <div className="card"><div className="text-xs text-institutional-muted">DEVELOPING SETUPS</div><div className="text-2xl font-semibold text-amber-300 mt-1 tabular-nums">{scanner?.developing ?? 0}</div><div className="text-[11px] text-institutional-muted mt-1">Awaiting confirmation</div></div>
        <div className="card"><div className="text-xs text-institutional-muted">NO SETUP</div><div className="text-2xl font-semibold text-slate-300 mt-1 tabular-nums">{scanner?.no_setup ?? 0}</div><div className="text-[11px] text-institutional-muted mt-1">No valid trade conditions</div></div>
      </section>

      <section className="card">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
          <div><div className="font-semibold">SCAN EXECUTION STATUS</div><div className="text-xs text-institutional-muted mt-1">Instrument totals update from completed backend scans. No estimated progress is displayed.</div></div>
          <span className={scanner?.scanning || loading ? "text-xs font-semibold text-cyan-300" : "text-xs text-institutional-muted"}>{scanner?.scanning ? "BACKEND SCAN RUNNING" : loading ? "MANUAL REQUEST PENDING" : "IDLE"}</span>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <span className="text-institutional-muted">Latest completed run</span>
          <span className="font-medium tabular-nums">{scanner?.scanned ?? results.length} instruments · {formatTime(scanner?.last_scan_utc)}</span>
        </div>
      </section>

      <PriceChart symbol={selected} timeframe="15M" />

      {selectedResult?.data_quality && (
        <section className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          <div className="card"><div className="text-xs text-institutional-muted mb-1">FEED STATUS</div><div className={selectedResult.data_quality.is_valid && !selectedResult.data_quality.stale ? "text-emerald-300 font-semibold" : "text-amber-300 font-semibold"}>{selectedResult.data_quality.market_status === "market_closed" ? "MARKET CLOSED" : selectedResult.data_quality.stale ? "STALE" : selectedResult.data_quality.is_valid ? "FRESH" : "UNAVAILABLE"}</div><div className="text-xs text-institutional-muted mt-1">{selectedResult.data_quality.message || "Feed quality not reported"}</div></div>
          <div className="card"><div className="text-xs text-institutional-muted mb-1">DATA PROVIDER</div><div className="text-sm font-medium break-words">{selectedResult.data_quality.provider || "Unknown"}</div></div>
          <div className="card"><div className="text-xs text-institutional-muted mb-1">LAST CANDLE (UTC)</div><div className="text-sm font-medium">{formatTime(selectedResult.data_quality.last_timestamp)}</div></div>
        </section>
      )}

      <section className="card overflow-x-auto">
        <div className="flex items-center justify-between mb-3">
          <div><div className="font-semibold">INSTRUMENT RESULTS</div><div className="text-xs text-institutional-muted mt-1">Select a market to load its TradingView chart.</div></div>
          <div className="text-xs text-institutional-muted">15-minute analysis</div>
        </div>
        <table className="w-full text-sm min-w-[760px]">
          <thead><tr className="text-left text-institutional-muted border-b border-institutional-border"><th className="pb-3 pr-4">Symbol</th><th className="pb-3 pr-4">Price</th><th className="pb-3 pr-4">Bias</th><th className="pb-3 pr-4">P/D</th><th className="pb-3 pr-4">SMT</th><th className="pb-3 pr-4">Status</th><th className="pb-3 pr-4">Model / Score</th><th className="pb-3">Notes</th></tr></thead>
          <tbody>
            {results.length === 0 && <tr><td colSpan={8} className="py-8 text-center text-institutional-muted">No persisted scan results are available yet. Scheduled scans populate this table automatically.</td></tr>}
            {results.map((item) => <tr key={item.symbol} onClick={() => setSelected(item.symbol)} className={selected === item.symbol ? "border-b border-institutional-border/60 bg-cyan-950/20 cursor-pointer" : "border-b border-institutional-border/60 hover:bg-white/[0.02] cursor-pointer"}>
              <td className="py-3 pr-4 font-semibold">{item.symbol}</td>
              <td className="py-3 pr-4 tabular-nums">{item.current_price == null ? "—" : item.current_price.toFixed(5)}</td>
              <td className="py-3 pr-4 capitalize">{item.bias || "—"}</td>
              <td className="py-3 pr-4 capitalize">{item.premium_discount || "—"}</td>
              <td className="py-3 pr-4 text-xs">{item.smt?.divergence || "—"}</td>
              <td className="py-3 pr-4"><span className={statusBadge(item.setup_status)}>{item.setup_status}</span></td>
              <td className="py-3 pr-4 text-xs">{item.best_setup ? <><div>{item.best_setup.model}</div><div className="text-institutional-muted">{item.best_setup.direction} · Score {item.best_setup.score ?? item.best_setup.score_breakdown?.total ?? "—"}</div></> : "—"}</td>
              <td className="py-3 text-xs text-institutional-muted max-w-xs truncate">{(item.notes || []).join(" · ") || item.error || "—"}</td>
            </tr>)}
          </tbody>
        </table>
      </section>

      <section className="card">
        <div className="font-semibold mb-3">PERSISTED SCAN HISTORY</div>
        <div className="space-y-2">
          {(scanner?.recent_scans || []).slice(0, 6).map((scan, index) => <div key={scan.timestamp_utc + index} className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 border-b border-institutional-border/60 pb-2 last:border-0">
            <div><div className="text-sm font-medium">{formatTime(scan.timestamp_utc)}</div><div className="text-[11px] text-institutional-muted">{scan.source === "scheduled" ? "GitHub Actions scheduled run" : scan.source === "manual" ? "Manual scan" : "Legacy scan"}{scan.workflow_run_id ? ` · Run #${scan.workflow_run_id}` : ""}</div></div>
            <div className="text-xs tabular-nums text-institutional-muted">{scan.scanned} instruments · {scan.confirmed} confirmed · {scan.developing} developing · {scan.no_setup} no setup</div>
          </div>)}
          {(!scanner?.recent_scans || scanner.recent_scans.length === 0) && <div className="text-xs text-institutional-muted">No scan snapshots returned by persistent storage.</div>}
        </div>
      </section>

      <p className="text-[11px] text-institutional-muted text-center px-2">Backend: {API_BASE}. Scheduled status is based on persisted GitHub Actions scan provenance. TradingView charts use their own spot-market data feed; scanner signals require the configured licensed market-data entitlement. No generated candles or futures substitution.</p>
    </div>
  );
}
