"use client";

import { useTradingStore } from "@/lib/store";
import { SignalCard } from "./SignalCard";
import {
  cn,
  formatNumber,
  formatTimestamp,
  getSignalColorClass,
} from "@/lib/utils";
import { Activity, RefreshCw } from "lucide-react";
import { CollapsibleSection } from "@/components/CollapsibleSection";

export function ScanResults() {
  const { scanResult, isLoading, runScan } = useTradingStore();
  const isScanning = isLoading.scan;
  const tradeSignal = scanResult?.tradeSignal || "hold";

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-zinc-100 flex items-center gap-2">
          <Activity className="w-5 h-5" />
          Market Analysis
        </h2>
        <button
          onClick={runScan}
          disabled={isScanning}
          className={cn(
            "flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors",
            "bg-primary-600 hover:bg-primary-700 text-white",
            "disabled:opacity-50 disabled:cursor-not-allowed"
          )}
        >
          <RefreshCw className={cn("w-4 h-4", isScanning && "animate-spin")} />
          {isScanning ? "Scanning..." : "Run Scan"}
        </button>
      </div>

      {/* Summary Card */}
      {scanResult && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-lg font-semibold text-zinc-100">
                {scanResult.symbol}
              </h3>
              <p className="text-sm text-zinc-500">
                {scanResult.exchange} | {scanResult.timeframe}
              </p>
            </div>

            <div className="text-right">
              <div
                className={cn(
                  "text-2xl font-bold px-4 py-2 rounded-lg inline-block",
                  getSignalColorClass(tradeSignal)
                )}
              >
                {tradeSignal.replace("_", " ").toUpperCase()}
              </div>
              <p className="text-sm text-zinc-500 mt-1">
                Score: {formatNumber(scanResult.scoreTotal, 1)}
              </p>
            </div>
          </div>

          {/* OHLCV Summary */}
          <div className="grid grid-cols-5 gap-4 p-3 bg-zinc-800/50 rounded-lg text-sm">
            <div>
              <div className="text-zinc-500">Open</div>
              <div className="text-zinc-200 font-mono">
                ${formatNumber(scanResult.ohlcv.open)}
              </div>
            </div>
            <div>
              <div className="text-zinc-500">High</div>
              <div className="text-zinc-200 font-mono">
                ${formatNumber(scanResult.ohlcv.high)}
              </div>
            </div>
            <div>
              <div className="text-zinc-500">Low</div>
              <div className="text-zinc-200 font-mono">
                ${formatNumber(scanResult.ohlcv.low)}
              </div>
            </div>
            <div>
              <div className="text-zinc-500">Close</div>
              <div className="text-zinc-200 font-mono">
                ${formatNumber(scanResult.ohlcv.close)}
              </div>
            </div>
            <div>
              <div className="text-zinc-500">Volume</div>
              <div className="text-zinc-200 font-mono">
                {formatNumber(scanResult.ohlcv.volume, 0)}
              </div>
            </div>
          </div>

          <p className="text-xs text-zinc-600 mt-2">
            Last updated: {formatTimestamp(scanResult.timestamp)}
          </p>
        </div>
      )}

      {/* Indicator Grid */}
      {scanResult && scanResult.indicators.length > 0 && (
        <CollapsibleSection
          title={`Indicators (${scanResult.indicators.length})`}
          icon={<Activity className="w-4 h-4 text-zinc-400" />}
          className="p-4"
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
      )}

      {/* Empty state */}
      {!scanResult && !isScanning && (
        <div className="card text-center py-8">
          <Activity className="w-12 h-12 mx-auto text-zinc-600 mb-4" />
          <p className="text-zinc-400">
            Select a symbol and click &quot;Run Scan&quot; to analyze the market
          </p>
        </div>
      )}
    </div>
  );
}
