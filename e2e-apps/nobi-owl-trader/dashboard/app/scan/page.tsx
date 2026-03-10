"use client";

import { useState } from "react";
import { Navigation } from "@/components/Navigation";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useTradingStore } from "@/lib/store";
import { SignalCard } from "@/components/SignalCard";
import { CollapsibleSection } from "@/components/CollapsibleSection";
import {
  cn,
  formatNumber,
  formatTimestamp,
  getSignalColorClass,
  COMMON_SYMBOLS,
  TIMEFRAMES,
} from "@/lib/utils";
import { ScanSearch, RefreshCw, Play, Clock, Layers, Activity } from "lucide-react";

export default function ScanPage() {
  const {
    scanResult,
    isLoading,
    runScan,
    setSelectedSymbol,
    setSelectedTimeframe,
    selectedSymbol,
    selectedTimeframe,
  } = useTradingStore();
  const isScanning = isLoading.scan;
  const tradeSignal = scanResult?.tradeSignal || "hold";

  const [multiScan, setMultiScan] = useState(false);
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>(["BTC/USDT"]);

  const handleSymbolToggle = (symbol: string) => {
    if (selectedSymbols.includes(symbol)) {
      setSelectedSymbols(selectedSymbols.filter((s) => s !== symbol));
    } else {
      setSelectedSymbols([...selectedSymbols, symbol]);
    }
  };

  const handleScan = () => {
    if (!multiScan) {
      runScan();
    } else {
      // For multi-scan, just run the first one for now
      // In a real implementation, this would scan all selected symbols
      if (selectedSymbols.length > 0) {
        setSelectedSymbol(selectedSymbols[0]);
        setTimeout(runScan, 100);
      }
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950">
      <Navigation />

      <main className="max-w-7xl mx-auto px-4 py-8">
        <ErrorBanner />

        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl flex items-center justify-center">
              <ScanSearch className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-zinc-100">Market Scanner</h1>
              <p className="text-zinc-500">
                Analyze markets with 27 technical indicators
              </p>
            </div>
          </div>

          <button
            onClick={handleScan}
            disabled={isScanning}
            className={cn(
              "flex items-center gap-2 px-6 py-3 rounded-xl font-medium transition-all",
              "bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-500 hover:to-emerald-500",
              "text-white shadow-lg shadow-green-500/25",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            {isScanning ? (
              <RefreshCw className="w-5 h-5 animate-spin" />
            ) : (
              <Play className="w-5 h-5" />
            )}
            {isScanning ? "Scanning..." : "Run Scan"}
          </button>
        </div>

        {/* Scan Configuration */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          {/* Symbol Selection */}
          <div className="lg:col-span-2 card">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-zinc-100 flex items-center gap-2">
                <Layers className="w-5 h-5 text-zinc-400" />
                Select Symbols
              </h3>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={multiScan}
                  onChange={(e) => setMultiScan(e.target.checked)}
                  className="w-4 h-4 rounded bg-zinc-800 border-zinc-700"
                />
                <span className="text-zinc-400">Multi-scan mode</span>
              </label>
            </div>

            {multiScan ? (
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                {COMMON_SYMBOLS.map((symbol) => (
                  <button
                    key={symbol}
                    onClick={() => handleSymbolToggle(symbol)}
                    className={cn(
                      "px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                      selectedSymbols.includes(symbol)
                        ? "bg-green-600 text-white"
                        : "bg-zinc-800 text-zinc-400 hover:text-zinc-200"
                    )}
                  >
                    {symbol.replace("/USDT", "")}
                  </button>
                ))}
              </div>
            ) : (
              <select
                value={selectedSymbol}
                onChange={(e) => setSelectedSymbol(e.target.value)}
                className="w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100 text-lg focus:outline-none focus:ring-2 focus:ring-green-500"
              >
                {COMMON_SYMBOLS.map((symbol) => (
                  <option key={symbol} value={symbol}>
                    {symbol}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Timeframe Selection */}
          <div className="card">
            <h3 className="font-semibold text-zinc-100 flex items-center gap-2 mb-4">
              <Clock className="w-5 h-5 text-zinc-400" />
              Timeframe
            </h3>
            <div className="grid grid-cols-3 gap-2">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf.value}
                  onClick={() => setSelectedTimeframe(tf.value)}
                  className={cn(
                    "px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                    selectedTimeframe === tf.value
                      ? "bg-green-600 text-white"
                      : "bg-zinc-800 text-zinc-400 hover:text-zinc-200"
                  )}
                >
                  {tf.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Scan Results */}
        {scanResult && (
          <>
            {/* Summary Card */}
            <div className="card mb-6">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-2xl font-bold text-zinc-100">
                    {scanResult.symbol}
                  </h2>
                  <p className="text-zinc-500">
                    {scanResult.exchange} | {scanResult.timeframe} | Last updated:{" "}
                    {formatTimestamp(scanResult.timestamp)}
                  </p>
                </div>

                <div className="text-right">
                  <div
                    className={cn(
                      "text-3xl font-bold px-6 py-3 rounded-xl inline-block",
                      getSignalColorClass(tradeSignal)
                    )}
                  >
                    {tradeSignal.replace("_", " ").toUpperCase()}
                  </div>
                  <p className="text-zinc-400 mt-2">
                    Aggregate Score:{" "}
                    <span
                      className={cn(
                        "font-bold text-lg",
                        scanResult.scoreTotal >= 0
                          ? "text-green-400"
                          : "text-red-400"
                      )}
                    >
                      {scanResult.scoreTotal > 0 ? "+" : ""}
                      {formatNumber(scanResult.scoreTotal, 1)}
                    </span>
                  </p>
                </div>
              </div>

              {/* OHLCV Bar */}
              <div className="grid grid-cols-5 gap-4 mt-6 p-4 bg-zinc-800/50 rounded-xl">
                <div>
                  <span className="text-zinc-500 text-sm">Open</span>
                  <p className="text-zinc-100 font-mono text-lg">
                    ${formatNumber(scanResult.ohlcv.open)}
                  </p>
                </div>
                <div>
                  <span className="text-zinc-500 text-sm">High</span>
                  <p className="text-green-400 font-mono text-lg">
                    ${formatNumber(scanResult.ohlcv.high)}
                  </p>
                </div>
                <div>
                  <span className="text-zinc-500 text-sm">Low</span>
                  <p className="text-red-400 font-mono text-lg">
                    ${formatNumber(scanResult.ohlcv.low)}
                  </p>
                </div>
                <div>
                  <span className="text-zinc-500 text-sm">Close</span>
                  <p className="text-zinc-100 font-mono text-lg">
                    ${formatNumber(scanResult.ohlcv.close)}
                  </p>
                </div>
                <div>
                  <span className="text-zinc-500 text-sm">Volume</span>
                  <p className="text-zinc-100 font-mono text-lg">
                    {formatNumber(scanResult.ohlcv.volume, 0)}
                  </p>
                </div>
              </div>
            </div>

            <CollapsibleSection
              title={`Indicator Breakdown (${scanResult.indicators.length} indicators)`}
              icon={<Activity className="w-4 h-4 text-zinc-400" />}
              className="p-4 mt-4"
              headerClassName="mb-3"
              bodyClassName="p-0"
              defaultOpen={true}
            >
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {scanResult.indicators.map((indicator) => (
                  <SignalCard key={indicator.name} indicator={indicator} />
                ))}
              </div>
            </CollapsibleSection>
          </>
        )}

        {/* Empty State */}
        {!scanResult && !isScanning && (
          <div className="card text-center py-16">
            <ScanSearch className="w-16 h-16 mx-auto text-zinc-700 mb-4" />
            <h3 className="text-xl font-semibold text-zinc-300 mb-2">
              Ready to Scan
            </h3>
            <p className="text-zinc-500 max-w-md mx-auto">
              Select a symbol and timeframe, then click &quot;Run Scan&quot; to analyze
              the market with 10 technical indicators.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
