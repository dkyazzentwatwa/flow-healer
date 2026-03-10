"use client";

import { useTradingStore } from "@/lib/store";
import { formatNumber, formatPercent, cn, getPriceColorClass } from "@/lib/utils";
import { TrendingUp, TrendingDown } from "lucide-react";

export function PriceDisplay() {
  const { ticker, selectedSymbol, isLoading } = useTradingStore();
  const isTickerLoading = isLoading.ticker;

  if (!ticker || isTickerLoading) {
    return (
      <div className="card">
        <div className="animate-pulse">
          <div className="h-8 bg-zinc-800 rounded w-32 mb-2"></div>
          <div className="h-4 bg-zinc-800 rounded w-20"></div>
        </div>
      </div>
    );
  }

  const isPositive = ticker.change >= 0;

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-1">
        <h2 className="text-lg font-semibold text-zinc-100">{selectedSymbol}</h2>
        {isPositive ? (
          <TrendingUp className="w-5 h-5 text-green-400" />
        ) : (
          <TrendingDown className="w-5 h-5 text-red-400" />
        )}
      </div>

      <div className="flex items-baseline gap-3">
        <span className="text-3xl font-bold text-zinc-100 font-mono">
          ${formatNumber(ticker.last)}
        </span>
        <span className={cn("text-lg font-medium", getPriceColorClass(ticker.change))}>
          {formatPercent(ticker.change)}
        </span>
      </div>

      <div className="grid grid-cols-4 gap-4 mt-4 text-sm">
        <div>
          <div className="text-zinc-500">High</div>
          <div className="text-zinc-200 font-mono">${formatNumber(ticker.high)}</div>
        </div>
        <div>
          <div className="text-zinc-500">Low</div>
          <div className="text-zinc-200 font-mono">${formatNumber(ticker.low)}</div>
        </div>
        <div>
          <div className="text-zinc-500">Bid</div>
          <div className="text-zinc-200 font-mono">${formatNumber(ticker.bid)}</div>
        </div>
        <div>
          <div className="text-zinc-500">Ask</div>
          <div className="text-zinc-200 font-mono">${formatNumber(ticker.ask)}</div>
        </div>
      </div>
    </div>
  );
}
