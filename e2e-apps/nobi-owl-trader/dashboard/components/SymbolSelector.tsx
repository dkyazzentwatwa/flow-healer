"use client";

import { useTradingStore } from "@/lib/store";
import { COMMON_SYMBOLS, TIMEFRAMES } from "@/lib/utils";

export function SymbolSelector() {
  const {
    selectedSymbol,
    selectedTimeframe,
    setSymbol,
    setSelectedSymbol,
    setSelectedTimeframe,
  } = useTradingStore();

  const handleSymbolChange = (symbol: string) => {
    if (typeof setSelectedSymbol === "function") {
      setSelectedSymbol(symbol);
      return;
    }
    if (typeof setSymbol === "function") {
      setSymbol(symbol);
    }
  };

  const handleTimeframeChange = (timeframe: string) => {
    if (typeof setSelectedTimeframe === "function") {
      setSelectedTimeframe(timeframe);
    }
  };

  return (
    <div className="card">
      <div className="grid grid-cols-2 gap-4">
        {/* Symbol Select */}
        <div>
          <label className="block text-sm font-medium text-zinc-400 mb-2">
            Symbol
          </label>
          <select
            value={selectedSymbol}
            onChange={(e) => handleSymbolChange(e.target.value)}
            className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            {COMMON_SYMBOLS.map((symbol) => (
              <option key={symbol} value={symbol}>
                {symbol}
              </option>
            ))}
          </select>
        </div>

        {/* Timeframe Select */}
        <div>
          <label className="block text-sm font-medium text-zinc-400 mb-2">
            Timeframe
          </label>
          <select
            value={selectedTimeframe}
            onChange={(e) => handleTimeframeChange(e.target.value)}
            className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            {TIMEFRAMES.map((tf) => (
              <option key={tf.value} value={tf.value}>
                {tf.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
