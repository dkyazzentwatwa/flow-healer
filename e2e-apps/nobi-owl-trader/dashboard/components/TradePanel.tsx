"use client";

import { useState } from "react";
import { useTradingStore } from "@/lib/store";
import { cn, formatNumber } from "@/lib/utils";
import { ArrowUpCircle, ArrowDownCircle } from "lucide-react";

export function TradePanel() {
  const {
    selectedSymbol,
    ticker,
    balance,
    isPaperTrading,
    isLoading,
    placeTrade,
  } = useTradingStore();
  const isTrading = isLoading.trades;

  const [amount, setAmount] = useState("");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [lastOrder, setLastOrder] = useState<{
    id: string;
    side: string;
    amount: number;
  } | null>(null);

  const handleTrade = async () => {
    if (!amount || parseFloat(amount) <= 0) return;

    try {
      const order = await placeTrade(side, parseFloat(amount));
      setLastOrder({
        id: order.id,
        side: order.side,
        amount: order.amount,
      });
      setAmount("");
    } catch (error) {
      console.error("Trade failed:", error);
    }
  };

  const [base, quote] = selectedSymbol.split("/");
  const quoteBalance = balance?.free[quote] || 0;
  const baseBalance = balance?.free[base] || 0;

  return (
    <div className="card">
      <div className="card-header flex items-center justify-between">
        <span>Quick Trade</span>
        {isPaperTrading && (
          <span className="px-2 py-0.5 text-xs bg-yellow-400/10 text-yellow-400 rounded">
            Paper Mode
          </span>
        )}
      </div>

      {/* Side Toggle */}
      <div className="grid grid-cols-2 gap-2 mb-4">
        <button
          onClick={() => setSide("buy")}
          className={cn(
            "flex items-center justify-center gap-2 py-3 rounded-lg font-medium transition-colors",
            side === "buy"
              ? "bg-green-600 text-white"
              : "bg-zinc-800 text-zinc-400 hover:text-zinc-200"
          )}
        >
          <ArrowUpCircle className="w-5 h-5" />
          Buy
        </button>
        <button
          onClick={() => setSide("sell")}
          className={cn(
            "flex items-center justify-center gap-2 py-3 rounded-lg font-medium transition-colors",
            side === "sell"
              ? "bg-red-600 text-white"
              : "bg-zinc-800 text-zinc-400 hover:text-zinc-200"
          )}
        >
          <ArrowDownCircle className="w-5 h-5" />
          Sell
        </button>
      </div>

      {/* Amount Input */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-zinc-400 mb-2">
          Amount ({base})
        </label>
        <input
          type="number"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="0.00"
          step="0.0001"
          min="0"
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100 font-mono focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
        <div className="flex justify-between text-xs text-zinc-500 mt-1">
          <span>
            Available: {formatNumber(side === "buy" ? quoteBalance : baseBalance, 4)}{" "}
            {side === "buy" ? quote : base}
          </span>
          {ticker && (
            <span>
              Est. value: ${formatNumber(parseFloat(amount || "0") * ticker.last)}
            </span>
          )}
        </div>
      </div>

      {/* Trade Button */}
      <button
        onClick={handleTrade}
        disabled={isTrading || !amount || parseFloat(amount) <= 0}
        className={cn(
          "w-full py-3 rounded-lg font-medium transition-colors",
          side === "buy"
            ? "bg-green-600 hover:bg-green-700"
            : "bg-red-600 hover:bg-red-700",
          "text-white disabled:opacity-50 disabled:cursor-not-allowed"
        )}
      >
        {isTrading
          ? "Processing..."
          : `${side === "buy" ? "Buy" : "Sell"} ${base}`}
      </button>

      {/* Last Order */}
      {lastOrder && (
        <div className="mt-4 p-3 bg-zinc-800/50 rounded-lg text-sm">
          <p className="text-zinc-400">Last Order:</p>
          <p className="text-zinc-200">
            {lastOrder.side.toUpperCase()} {formatNumber(lastOrder.amount, 8)}{" "}
            {base}
          </p>
          <p className="text-xs text-zinc-500">ID: {lastOrder.id}</p>
        </div>
      )}
    </div>
  );
}
