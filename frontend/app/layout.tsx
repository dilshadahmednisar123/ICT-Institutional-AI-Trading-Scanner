import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ICT Institutional AI Trading Scanner",
  description: "Signal-only ICT scanner. Selective. NO TRADE is preferred when conditions fail.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <header className="border-b border-institutional-border bg-institutional-panel/80 backdrop-blur sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center font-bold text-sm">
                ICT
              </div>
              <div>
                <div className="font-semibold tracking-tight">Institutional AI Scanner</div>
                <div className="text-xs text-institutional-muted">Signal Only · Selective · No Forced Trades</div>
              </div>
            </div>
            <div className="text-xs text-institutional-muted">v0.4.0</div>
          </div>
        </header>
        <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
