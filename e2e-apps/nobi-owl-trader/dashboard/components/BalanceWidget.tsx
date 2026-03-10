"use client";

import { useTradingStore } from "@/lib/store";
import { formatNumber } from "@/lib/utils";
import { Wallet } from "lucide-react";

export function BalanceWidget() {
  const { balance, isPaperTrading } = useTradingStore();

  if (!balance) {
    return (
      <div className="card">
        <div className="card-header flex items-center gap-2">
          <Wallet className="w-5 h-5" />
          Account Balance
        </div>
        <p className="text-zinc-500">Loading...</p>
      </div>
    );
  }

  // Get non-zero balances
  const nonZeroBalances = Object.entries(balance.total)
    .filter(([_, amount]) => amount > 0)
    .sort((a, b) => b[1] - a[1]);

  return (
    <div className="card">
      <div className="card-header flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Wallet className="w-5 h-5" />
          Account Balance
        </div>
        {isPaperTrading && (
          <span className="px-2 py-0.5 text-xs bg-yellow-400/10 text-yellow-400 rounded">
            Paper Trading
          </span>
        )}
      </div>

      {nonZeroBalances.length === 0 ? (
        <p className="text-zinc-500">No assets</p>
      ) : (
        <div className="space-y-2">
          {nonZeroBalances.map(([asset, total]) => (
            <div
              key={asset}
              className="flex items-center justify-between p-2 bg-zinc-800/50 rounded"
            >
              <div>
                <span className="font-medium text-zinc-200">{asset}</span>
                <div className="text-xs text-zinc-500">
                  Free: {formatNumber(balance.free[asset] || 0, 4)}
                </div>
              </div>
              <div className="text-right">
                <span className="font-mono text-zinc-100">
                  {formatNumber(total, asset === "USDT" ? 2 : 8)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
