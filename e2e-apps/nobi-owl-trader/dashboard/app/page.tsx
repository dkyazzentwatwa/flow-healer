"use client";

import { useEffect } from "react";
import { useTradingStore } from "@/lib/store";
import { Navigation } from "@/components/Navigation";
import { ErrorBanner } from "@/components/ErrorBanner";
import { SymbolSelector } from "@/components/SymbolSelector";
import { PriceDisplay } from "@/components/PriceDisplay";
import { BalanceWidget } from "@/components/BalanceWidget";
import { TradePanel } from "@/components/TradePanel";
import { ScanResults } from "@/components/ScanResults";
import { LogViewer } from "@/components/LogViewer";
import { TradingChart } from "@/components/TradingChart";
import { TrendingUp, TrendingDown, Activity, Zap } from "lucide-react";
import { cn, formatNumber, formatPercent } from "@/lib/utils";

// Quick stats component
function QuickStats() {
  const { scanResult, ticker } = useTradingStore();

  const stats = [
    {
      label: "Current Price",
      value: ticker ? `$${formatNumber(ticker.last)}` : "—",
      change: ticker?.change,
      icon: TrendingUp,
    },
    {
      label: "24h Change",
      value: ticker ? formatPercent(ticker.change) : "—",
      positive: ticker ? ticker.change >= 0 : null,
      icon: ticker && ticker.change >= 0 ? TrendingUp : TrendingDown,
    },
    {
      label: "Signal Score",
      value: scanResult ? formatNumber(scanResult.scoreTotal, 1) : "—",
      positive: scanResult ? scanResult.scoreTotal >= 0 : null,
      icon: Zap,
    },
    {
      label: "Indicators",
      value: scanResult ? `${scanResult.indicators.length} Active` : "—",
      icon: Activity,
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {stats.map((stat, i) => {
        const Icon = stat.icon;
        return (
          <div
            key={i}
            className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-zinc-500 text-sm">{stat.label}</span>
              <Icon
                className={cn(
                  "w-4 h-4",
                  stat.positive === true
                    ? "text-green-400"
                    : stat.positive === false
                    ? "text-red-400"
                    : "text-zinc-500"
                )}
              />
            </div>
            <div
              className={cn(
                "text-xl font-bold font-mono",
                stat.positive === true
                  ? "text-green-400"
                  : stat.positive === false
                  ? "text-red-400"
                  : "text-zinc-100"
              )}
            >
              {stat.value}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function Dashboard() {
  const { fetchBalance, fetchTicker, selectedSymbol, isConnected } =
    useTradingStore();

  // Fetch data on mount and when symbol changes
  useEffect(() => {
    if (isConnected) {
      fetchBalance();
      fetchTicker();
    }
  }, [isConnected, selectedSymbol, fetchBalance, fetchTicker]);

  // Auto-refresh ticker every 10 seconds
  useEffect(() => {
    if (!isConnected) return;

    const interval = setInterval(() => {
      fetchTicker();
    }, 10000);

    return () => clearInterval(interval);
  }, [isConnected, fetchTicker]);

  return (
    <div className="min-h-screen bg-zinc-950">
      <Navigation />

      <main className="max-w-7xl mx-auto px-4 py-6">
        {/* Error Banner */}
        <ErrorBanner />

        {/* Symbol & Price Row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
          <div className="lg:col-span-2">
            <SymbolSelector />
          </div>
          <div>
            <PriceDisplay />
          </div>
        </div>

        {/* Quick Stats */}
        <QuickStats />

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Left Sidebar */}
          <div className="space-y-4">
            <BalanceWidget />
            <TradePanel />
          </div>

          {/* Main Content */}
          <div className="lg:col-span-3 space-y-6">
            <TradingChart />
            <ScanResults />
            <LogViewer />
          </div>
        </div>

        {/* Footer */}
        <footer className="mt-8 pt-4 border-t border-zinc-800">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4 text-xs text-zinc-600">
            <p>
              NobiBot v2.0 - Professional Cryptocurrency Trading Bot with 22
              Technical Indicators
            </p>
            <p>
              Warning: Trading involves significant risk. Paper trading
              recommended for testing.
            </p>
          </div>
        </footer>
      </main>
    </div>
  );
}
