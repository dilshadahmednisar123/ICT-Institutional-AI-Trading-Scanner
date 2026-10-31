import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "LIQUIDITY NEXUS — Decode Liquidity. Follow Smart Money.",
  description: "Institutional-style ICT market scanner for Forex and Gold. Signal-only analysis with liquidity-based risk levels.",
  applicationName: "LIQUIDITY NEXUS",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/liquidity-nexus-mark.svg", apple: "/liquidity-nexus-mark.svg" },
  themeColor: "#07111f",
};
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body className="min-h-screen antialiased">
    <header className="border-b border-institutional-border bg-institutional-panel/90 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <img src="/liquidity-nexus-mark.svg" alt="Liquidity Nexus" width="42" height="42" />
          <div><div className="font-semibold tracking-[0.12em] text-sm sm:text-base">LIQUIDITY NEXUS</div>
          <div className="text-[10px] sm:text-xs text-institutional-muted">Decode Liquidity. Follow Smart Money.</div></div>
        </div>
        <div className="text-[10px] sm:text-xs text-cyan-300 border border-cyan-900/70 rounded-full px-3 py-1">SIGNAL ONLY</div>
      </div>
    </header>
    <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
  </body></html>;
}
