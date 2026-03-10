"use client";

import { useEffect, useState } from "react";
import { Navigation } from "@/components/Navigation";
import { useTradingStore } from "@/lib/store";
import { formatNumber, formatTimestamp, cn } from "@/lib/utils";
import { Modal } from "@/components/Modal";
import { ScanResult, Trade } from "@/lib/types";
import {
  History,
  ArrowUpCircle,
  ArrowDownCircle,
  Search,
  Trash2,
  Download,
} from "lucide-react";

export default function HistoryPage() {
  const {
    allTrades,
    fetchAllTrades,
    isLoading,
    tradeHistory,
    scanHistory,
    loadHistory,
    clearTradeHistory,
    clearScanHistory,
  } = useTradingStore();

  const [tab, setTab] = useState<"trades" | "scans">("trades");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const [selectedScan, setSelectedScan] = useState<ScanResult | null>(null);

  // Load history from localStorage on mount
  useEffect(() => {
    loadHistory();
    fetchAllTrades();
  }, [loadHistory, fetchAllTrades]);

  const trades = allTrades.length > 0 ? allTrades : tradeHistory;

  const pnlByTradeId = (() => {
    const map = new Map<string, { pnl: number; pnlPct: number }>();
    const lots: { amount: number; price: number }[] = [];
    const ordered = [...trades].sort((a, b) => a.timestamp - b.timestamp);

    for (const trade of ordered) {
      if (trade.side === "buy") {
        lots.push({ amount: trade.amount, price: trade.price });
        map.set(trade.id, { pnl: 0, pnlPct: 0 });
        continue;
      }

      let remaining = trade.amount;
      let pnl = 0;
      let cost = 0;

      while (remaining > 0 && lots.length > 0) {
        const lot = lots[0];
        const used = Math.min(remaining, lot.amount);
        pnl += (trade.price - lot.price) * used;
        cost += lot.price * used;
        lot.amount -= used;
        remaining -= used;
        if (lot.amount <= 0) {
          lots.shift();
        }
      }

      if (remaining > 0) {
        cost += trade.price * remaining;
      }

      const pnlPct = cost > 0 ? (pnl / cost) * 100 : 0;
      map.set(trade.id, { pnl, pnlPct });
    }

    return map;
  })();

  const realizedPnlTotal = trades.reduce((acc, trade) => {
    const pnl = pnlByTradeId.get(trade.id)?.pnl ?? 0;
    return acc + pnl;
  }, 0);

  const filteredTrades = trades.filter((trade) =>
    trade.symbol.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredScans = scanHistory.filter((scan) =>
    scan.symbol.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Export to CSV
  const exportToCSV = () => {
    if (tab === "trades") {
      const headers = "Date,Symbol,Side,Amount,Price,Total,PnL,PnL%,Status,Paper\n";
      const rows = trades
        .map(
          (t) => {
            const pnl = pnlByTradeId.get(t.id)?.pnl ?? 0;
            const pnlPct = pnlByTradeId.get(t.id)?.pnlPct ?? 0;
            return `${t.timestamp},${t.symbol},${t.side},${t.amount},${t.price},${t.total},${pnl},${pnlPct},${t.status},${t.paper}`;
          }
        )
        .join("\n");
      downloadCSV(headers + rows, "nobibot-trades.csv");
    } else {
      const headers = "Date,Symbol,Timeframe,Signal,Score\n";
      const rows = scanHistory
        .map(
          (s) =>
            `${s.timestamp},${s.symbol},${s.timeframe},${s.tradeSignal},${s.scoreTotal}`
        )
        .join("\n");
      downloadCSV(headers + rows, "nobibot-scans.csv");
    }
  };

  const downloadCSV = (content: string, filename: string) => {
    const blob = new Blob([content], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="min-h-screen bg-zinc-950">
      <Navigation />

      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-8">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-zinc-800 rounded-xl flex items-center justify-center">
              <History className="w-6 h-6 text-zinc-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-zinc-100">History</h1>
              <p className="text-zinc-500">View past trades and scans</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={exportToCSV}
              className="flex items-center gap-2 px-3 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm text-zinc-300 transition-colors w-full sm:w-auto"
            >
              <Download className="w-4 h-4" />
              Export CSV
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-4 mb-6">
          <div className="flex bg-zinc-900 rounded-lg p-1 w-full sm:w-auto">
            <button
              onClick={() => setTab("trades")}
              className={cn(
                "px-4 py-2 rounded-md text-sm font-medium transition-colors",
                tab === "trades"
                  ? "bg-zinc-800 text-zinc-100"
                  : "text-zinc-400 hover:text-zinc-200"
              )}
            >
              Trade History ({trades.length})
            </button>
            <button
              onClick={() => setTab("scans")}
              className={cn(
                "px-4 py-2 rounded-md text-sm font-medium transition-colors",
                tab === "scans"
                  ? "bg-zinc-800 text-zinc-100"
                  : "text-zinc-400 hover:text-zinc-200"
              )}
            >
              Scan History ({scanHistory.length})
            </button>
          </div>

          <div className="flex-1" />

          {/* Search */}
          <div className="relative w-full sm:w-72">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <input
              type="text"
              placeholder="Search symbol..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 pr-4 py-2 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 w-full"
            />
          </div>

          {/* Clear button */}
          <button
            onClick={() => (tab === "trades" ? clearTradeHistory() : clearScanHistory())}
            className="flex items-center gap-2 px-3 py-2 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 rounded-lg text-sm text-red-400 transition-colors w-full sm:w-auto"
          >
            <Trash2 className="w-4 h-4" />
            Clear
          </button>
        </div>

        {/* Trade History */}
        {tab === "trades" && (
          <div className="card">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px]">
                <thead>
                  <tr className="text-left text-zinc-500 text-sm border-b border-zinc-800">
                    <th className="pb-3 font-medium">Date</th>
                    <th className="pb-3 font-medium">Symbol</th>
                    <th className="pb-3 font-medium">Side</th>
                    <th className="pb-3 font-medium text-right">Amount</th>
                    <th className="pb-3 font-medium text-right">Price</th>
                    <th className="pb-3 font-medium text-right">Total</th>
                    <th className="pb-3 font-medium text-right">P/L</th>
                    <th className="pb-3 font-medium text-right">P/L %</th>
                    <th className="pb-3 font-medium text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {isLoading.trades ? (
                    <tr>
                      <td colSpan={9} className="py-12 text-center text-zinc-500">
                        Loading trades...
                      </td>
                    </tr>
                  ) : filteredTrades.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="py-12 text-center text-zinc-500">
                        <History className="w-12 h-12 mx-auto mb-3 opacity-50" />
                        <p>No trades yet</p>
                        <p className="text-sm mt-1">
                          Your trade history will appear here
                        </p>
                      </td>
                    </tr>
                  ) : (
                    filteredTrades.map((trade) => (
                      <tr
                        key={trade.id}
                        className="text-zinc-300 cursor-pointer hover:bg-zinc-900/50 transition-colors"
                        onClick={() => setSelectedTrade(trade)}
                      >
                        <td className="py-3 text-sm">
                          {formatTimestamp(trade.timestamp)}
                        </td>
                        <td className="py-3 font-medium">{trade.symbol}</td>
                        <td className="py-3">
                          <span
                            className={cn(
                              "inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium",
                              trade.side === "buy"
                                ? "bg-green-400/10 text-green-400"
                                : "bg-red-400/10 text-red-400"
                            )}
                          >
                            {trade.side === "buy" ? (
                              <ArrowUpCircle className="w-3 h-3" />
                            ) : (
                              <ArrowDownCircle className="w-3 h-3" />
                            )}
                            {trade.side.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-3 text-right font-mono">
                          {formatNumber(trade.amount, 6)}
                        </td>
                        <td className="py-3 text-right font-mono">
                          ${formatNumber(trade.price)}
                        </td>
                        <td className="py-3 text-right font-mono">
                          ${formatNumber(trade.total)}
                        </td>
                        <td className={cn(
                          "py-3 text-right font-mono",
                          (pnlByTradeId.get(trade.id)?.pnl ?? 0) >= 0
                            ? "text-green-400"
                            : "text-red-400"
                        )}>
                          {trade.side === "sell"
                            ? `${(pnlByTradeId.get(trade.id)?.pnl ?? 0) >= 0 ? "+" : ""}${formatNumber(pnlByTradeId.get(trade.id)?.pnl ?? 0)}`
                            : "—"}
                        </td>
                        <td className={cn(
                          "py-3 text-right font-mono",
                          (pnlByTradeId.get(trade.id)?.pnlPct ?? 0) >= 0
                            ? "text-green-400"
                            : "text-red-400"
                        )}>
                          {trade.side === "sell"
                            ? `${(pnlByTradeId.get(trade.id)?.pnlPct ?? 0) >= 0 ? "+" : ""}${formatNumber(pnlByTradeId.get(trade.id)?.pnlPct ?? 0, 2)}%`
                            : "—"}
                        </td>
                        <td className="py-3 text-right">
                          <span className="inline-flex items-center gap-1">
                            <span
                              className={cn(
                                "w-2 h-2 rounded-full",
                                trade.status === "closed"
                                  ? "bg-green-400"
                                  : "bg-yellow-400"
                              )}
                            />
                            <span className="text-xs text-zinc-400">
                              {trade.status}
                            </span>
                            {trade.paper && (
                              <span className="ml-1 text-xs text-yellow-400">
                                (paper)
                              </span>
                            )}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Scan History */}
        {tab === "scans" && (
          <div className="card">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px]">
                <thead>
                  <tr className="text-left text-zinc-500 text-sm border-b border-zinc-800">
                    <th className="pb-3 font-medium">Date</th>
                    <th className="pb-3 font-medium">Symbol</th>
                    <th className="pb-3 font-medium">Timeframe</th>
                    <th className="pb-3 font-medium text-center">Signal</th>
                    <th className="pb-3 font-medium text-right">Score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {filteredScans.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-12 text-center text-zinc-500">
                        <History className="w-12 h-12 mx-auto mb-3 opacity-50" />
                        <p>No scans yet</p>
                        <p className="text-sm mt-1">
                          Run a market scan to see results here
                        </p>
                      </td>
                    </tr>
                  ) : (
                    filteredScans.map((scan) => (
                      <tr
                        key={`${scan.symbol}-${scan.timestamp}`}
                        className="text-zinc-300 cursor-pointer hover:bg-zinc-900/50 transition-colors"
                        onClick={() => setSelectedScan(scan)}
                      >
                        <td className="py-3 text-sm">
                          {formatTimestamp(scan.timestamp)}
                        </td>
                        <td className="py-3 font-medium">{scan.symbol}</td>
                        <td className="py-3 text-zinc-400">{scan.timeframe}</td>
                        <td className="py-3 text-center">
                          <span
                            className={cn(
                              "px-3 py-1 rounded text-xs font-medium uppercase",
                              scan.tradeSignal.includes("buy")
                                ? "bg-green-400/10 text-green-400"
                                : scan.tradeSignal.includes("sell")
                                ? "bg-red-400/10 text-red-400"
                                : "bg-yellow-400/10 text-yellow-400"
                            )}
                          >
                            {scan.tradeSignal.replace("_", " ")}
                          </span>
                        </td>
                        <td
                          className={cn(
                            "py-3 text-right font-mono",
                            scan.scoreTotal > 0
                              ? "text-green-400"
                              : scan.scoreTotal < 0
                              ? "text-red-400"
                              : "text-zinc-400"
                          )}
                        >
                          {scan.scoreTotal > 0 ? "+" : ""}
                          {formatNumber(scan.scoreTotal, 1)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Stats */}
        {tab === "trades" && trades.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
            <div className="card text-center">
              <p className="text-zinc-500 text-sm">Total Trades</p>
              <p className="text-2xl font-bold text-zinc-100">
                {trades.length}
              </p>
            </div>
            <div className="card text-center">
              <p className="text-zinc-500 text-sm">Buy Orders</p>
              <p className="text-2xl font-bold text-green-400">
                {trades.filter((t) => t.side === "buy").length}
              </p>
            </div>
            <div className="card text-center">
              <p className="text-zinc-500 text-sm">Sell Orders</p>
              <p className="text-2xl font-bold text-red-400">
                {trades.filter((t) => t.side === "sell").length}
              </p>
            </div>
            <div className="card text-center">
              <p className="text-zinc-500 text-sm">Realized P/L</p>
              <p className={cn(
                "text-2xl font-bold",
                realizedPnlTotal >= 0 ? "text-green-400" : "text-red-400"
              )}>
                {realizedPnlTotal >= 0 ? "+" : ""}{formatNumber(realizedPnlTotal)}
              </p>
            </div>
          </div>
        )}

        <p className="text-center text-zinc-600 text-sm mt-6">
          Trades are loaded from the server; scans are stored locally in your browser.
        </p>
      </main>

      <Modal
        isOpen={!!selectedTrade}
        onClose={() => setSelectedTrade(null)}
        title={`Trade Details${selectedTrade?.id ? ` • ${selectedTrade.id.slice(0, 8)}` : ""}`}
      >
        {selectedTrade && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-zinc-500">Date</p>
                <p className="text-zinc-100 font-mono">{formatTimestamp(selectedTrade.timestamp)}</p>
              </div>
              <div>
                <p className="text-zinc-500">Symbol</p>
                <p className="text-zinc-100 font-mono">{selectedTrade.symbol}</p>
              </div>
              <div>
                <p className="text-zinc-500">Side</p>
                <p className="text-zinc-100 uppercase">{selectedTrade.side}</p>
              </div>
              <div>
                <p className="text-zinc-500">Status</p>
                <p className="text-zinc-100">{selectedTrade.status}</p>
              </div>
              <div>
                <p className="text-zinc-500">Amount</p>
                <p className="text-zinc-100 font-mono">{formatNumber(selectedTrade.amount, 6)}</p>
              </div>
              <div>
                <p className="text-zinc-500">Price</p>
                <p className="text-zinc-100 font-mono">${formatNumber(selectedTrade.price)}</p>
              </div>
              <div>
                <p className="text-zinc-500">Total</p>
                <p className="text-zinc-100 font-mono">${formatNumber(selectedTrade.total)}</p>
              </div>
              <div>
                <p className="text-zinc-500">Fee</p>
                <p className="text-zinc-100 font-mono">
                  {selectedTrade.fee ? formatNumber(selectedTrade.fee, 6) : "—"}
                  {selectedTrade.feeCurrency ? ` ${selectedTrade.feeCurrency}` : ""}
                </p>
              </div>
              <div>
                <p className="text-zinc-500">Paper</p>
                <p className="text-zinc-100">{selectedTrade.paper ? "Yes" : "No"}</p>
              </div>
              <div>
                <p className="text-zinc-500">Strategy</p>
                <p className="text-zinc-100">{selectedTrade.strategy || "—"}</p>
              </div>
              <div>
                <p className="text-zinc-500">Stop Price</p>
                <p className="text-zinc-100 font-mono">
                  {selectedTrade.stopPrice ? `$${formatNumber(selectedTrade.stopPrice)}` : "—"}
                </p>
              </div>
              <div>
                <p className="text-zinc-500">Target Price</p>
                <p className="text-zinc-100 font-mono">
                  {selectedTrade.targetPrice ? `$${formatNumber(selectedTrade.targetPrice)}` : "—"}
                </p>
              </div>
              <div className="col-span-2">
                <p className="text-zinc-500">Notes</p>
                <p className="text-zinc-100">{selectedTrade.notes || "—"}</p>
              </div>
              <div>
                <p className="text-zinc-500">P/L</p>
                <p
                  className={cn(
                    "font-mono",
                    (pnlByTradeId.get(selectedTrade.id)?.pnl ?? 0) >= 0
                      ? "text-green-400"
                      : "text-red-400"
                  )}
                >
                  {selectedTrade.side === "sell"
                    ? `${(pnlByTradeId.get(selectedTrade.id)?.pnl ?? 0) >= 0 ? "+" : ""}${formatNumber(pnlByTradeId.get(selectedTrade.id)?.pnl ?? 0)}`
                    : "—"}
                </p>
              </div>
              <div>
                <p className="text-zinc-500">P/L %</p>
                <p
                  className={cn(
                    "font-mono",
                    (pnlByTradeId.get(selectedTrade.id)?.pnlPct ?? 0) >= 0
                      ? "text-green-400"
                      : "text-red-400"
                  )}
                >
                  {selectedTrade.side === "sell"
                    ? `${(pnlByTradeId.get(selectedTrade.id)?.pnlPct ?? 0) >= 0 ? "+" : ""}${formatNumber(pnlByTradeId.get(selectedTrade.id)?.pnlPct ?? 0, 2)}%`
                    : "—"}
                </p>
              </div>
            </div>
          </div>
        )}
      </Modal>

      <Modal
        isOpen={!!selectedScan}
        onClose={() => setSelectedScan(null)}
        title={`Scan Details${selectedScan?.symbol ? ` • ${selectedScan.symbol}` : ""}`}
      >
        {selectedScan && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-zinc-500">Date</p>
                <p className="text-zinc-100 font-mono">{formatTimestamp(selectedScan.timestamp)}</p>
              </div>
              <div>
                <p className="text-zinc-500">Timeframe</p>
                <p className="text-zinc-100 font-mono">{selectedScan.timeframe}</p>
              </div>
              <div>
                <p className="text-zinc-500">Signal</p>
                <p className="text-zinc-100 uppercase">{selectedScan.tradeSignal}</p>
              </div>
              <div>
                <p className="text-zinc-500">Score</p>
                <p className="text-zinc-100 font-mono">{formatNumber(selectedScan.scoreTotal, 1)}</p>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
              {Object.entries(selectedScan.ohlcv).map(([key, value]) => (
                <div key={key} className="bg-zinc-900/60 rounded-lg p-2 border border-zinc-800">
                  <p className="text-zinc-500 uppercase">{key}</p>
                  <p className="text-zinc-100 font-mono">{formatNumber(Number(value))}</p>
                </div>
              ))}
            </div>

            <div>
              <p className="text-zinc-500 text-sm mb-2">Indicators</p>
              <div className="max-h-64 overflow-y-auto border border-zinc-800 rounded-lg">
                <table className="w-full text-left text-xs">
                  <thead className="text-zinc-500 border-b border-zinc-800 bg-zinc-900/60">
                    <tr>
                      <th className="px-3 py-2">Name</th>
                      <th className="px-3 py-2 text-right">Value</th>
                      <th className="px-3 py-2 text-right">Score</th>
                      <th className="px-3 py-2">Signal</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/70">
                    {selectedScan.indicators.map((indicator) => (
                      <tr key={indicator.name} className="text-zinc-300">
                        <td className="px-3 py-2">{indicator.name}</td>
                        <td className="px-3 py-2 text-right font-mono">
                          {typeof indicator.value === "number"
                            ? formatNumber(indicator.value, 2)
                            : indicator.value}
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          {formatNumber(indicator.score, 2)}
                        </td>
                        <td className="px-3 py-2 uppercase text-zinc-400">{indicator.signal}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
