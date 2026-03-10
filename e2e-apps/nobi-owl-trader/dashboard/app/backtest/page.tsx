"use client";

import { useState, useEffect } from "react";
import { Navigation } from "@/components/Navigation";
import { useTradingStore } from "@/lib/store";
import { 
  FlaskConical, 
  Play, 
  Download, 
  TrendingUp, 
  TrendingDown, 
  BarChart2,
  AlertCircle,
  Loader2
} from "lucide-react";
import { cn, formatNumber, formatPercent } from "@/lib/utils";
import { TuningStatus } from "@/lib/types";
import { Modal } from "@/components/Modal";

export default function BacktestPage() {
  const { 
    automationRules, 
    fetchAutomationRules, 
    runBacktest, 
    downloadBacktestData,
    runTuning,
    fetchTuningStatus,
    isLoading 
  } = useTradingStore();

  const [selectedRuleId, setSelectedRuleId] = useState("");
  const [selectedExitRuleId, setSelectedExitRuleId] = useState<string>("");
  const [days, setDays] = useState(30);
  const [balance, setBalance] = useState(10000);
  const [results, setResults] = useState<any>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [autoDownload, setAutoDownload] = useState(true);
  const [selectedTrade, setSelectedTrade] = useState<any | null>(null);
  const [tuningStatus, setTuningStatus] = useState<TuningStatus | null>(null);
  const [tuningLoading, setTuningLoading] = useState(false);
  const [tuningModalOpen, setTuningModalOpen] = useState(false);
  const formatBacktestDate = (raw: number | null | undefined) => {
    if (!raw) return "—";
    const ts = raw > 1e12 ? raw : raw * 1000;
    return new Date(ts).toLocaleDateString();
  };

  useEffect(() => {
    fetchAutomationRules();
  }, [fetchAutomationRules]);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | undefined;
    const refresh = async () => {
      const status = await fetchTuningStatus();
      if (status) {
        setTuningStatus(status);
      }
    };
    refresh();
    interval = setInterval(() => {
      if (tuningStatus?.running) {
        refresh();
      }
    }, 6000);
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [fetchTuningStatus, tuningStatus?.running]);

  const handleRun = async () => {
    if (!selectedRuleId) return;
    setIsRunning(true);
    if (autoDownload) {
      const rule = automationRules.find(r => r.id === selectedRuleId);
      if (rule) {
        await downloadBacktestData(rule.symbol, rule.timeframe, days + 5);
      }
    }
    const res = await runBacktest(selectedRuleId, days, balance, selectedExitRuleId || undefined);
    setResults(res);
    setIsRunning(false);
  };

  const handleDownload = async () => {
    const rule = automationRules.find(r => r.id === selectedRuleId);
    if (!rule) return;
    setIsDownloading(true);
    await downloadBacktestData(rule.symbol, rule.timeframe, days + 5); // buffer
    setIsDownloading(false);
  };

  const handleRetune = async () => {
    setTuningLoading(true);
    await runTuning({
      autoApply: true,
      allSymbols: true,
      skipDownload: false,
      fast: false,
    });
    const status = await fetchTuningStatus();
    if (status) {
      setTuningStatus(status);
    }
    setTuningLoading(false);
    setTuningModalOpen(true);
  };

  const selectedEntryRule = automationRules.find(r => r.id === selectedRuleId);
  const exitRuleOptions = selectedEntryRule
    ? automationRules.filter(
        (r) =>
          r.side === "sell" &&
          r.symbol === selectedEntryRule.symbol &&
          r.timeframe === selectedEntryRule.timeframe
      )
    : [];

  useEffect(() => {
    if (!selectedEntryRule) {
      setSelectedExitRuleId("");
      return;
    }
    if (exitRuleOptions.length === 0) {
      setSelectedExitRuleId("");
      return;
    }
    if (!exitRuleOptions.find((rule) => rule.id === selectedExitRuleId)) {
      setSelectedExitRuleId(exitRuleOptions[0].id);
    }
  }, [selectedRuleId, selectedEntryRule, exitRuleOptions, selectedExitRuleId]);

  return (
    <div className="min-h-screen bg-zinc-950">
      <Navigation />
      
      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-12 h-12 bg-blue-500/10 rounded-xl flex items-center justify-center">
            <FlaskConical className="w-6 h-6 text-blue-500" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-zinc-100">Backtesting Lab</h1>
            <p className="text-zinc-500">Test your strategies against historical market data</p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Configuration Sidebar */}
          <div className="lg:col-span-1 space-y-6">
            <div className="card">
              <h3 className="text-sm font-bold text-zinc-400 uppercase tracking-wider mb-4">Configuration</h3>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-xs text-zinc-500 mb-1.5 uppercase">Select Rule</label>
                  <select 
                    value={selectedRuleId}
                    onChange={e => setSelectedRuleId(e.target.value)}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 outline-none"
                  >
                    <option value="">Choose a strategy...</option>
                    {automationRules.map(rule => (
                      <option key={rule.id} value={rule.id}>{rule.name} ({rule.symbol})</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs text-zinc-500 mb-1.5 uppercase">Exit Rule (Optional)</label>
                  <select
                    value={selectedExitRuleId}
                    onChange={e => setSelectedExitRuleId(e.target.value)}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 outline-none"
                    disabled={!selectedEntryRule}
                  >
                    <option value="">None</option>
                    {exitRuleOptions.map(rule => (
                      <option key={rule.id} value={rule.id}>{rule.name}</option>
                    ))}
                  </select>
                  {!selectedEntryRule && (
                    <p className="text-xs text-zinc-600 mt-1">Select an entry rule to see matching exits.</p>
                  )}
                </div>

                <div>
                  <label className="block text-xs text-zinc-500 mb-1.5 uppercase">Duration (Days)</label>
                  <input 
                    type="number"
                    value={days}
                    onChange={e => setDays(parseInt(e.target.value))}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 outline-none"
                  />
                </div>

                <div>
                  <label className="block text-xs text-zinc-500 mb-1.5 uppercase">Initial Balance ($)</label>
                  <input 
                    type="number"
                    value={balance}
                    onChange={e => setBalance(parseInt(e.target.value))}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 outline-none"
                  />
                </div>

                <label className="flex items-center gap-2 text-xs text-zinc-400">
                  <input
                    type="checkbox"
                    checked={autoDownload}
                    onChange={(e) => setAutoDownload(e.target.checked)}
                    className="w-4 h-4 rounded border-zinc-600"
                  />
                  Auto-download historical data before running
                </label>

                <div className="pt-2 space-y-2">
                  <button 
                    onClick={handleDownload}
                    disabled={!selectedRuleId || isDownloading}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-zinc-200 rounded-lg font-medium transition-all"
                  >
                    {isDownloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                    Download Data
                  </button>
                  
                  <button 
                    onClick={handleRun}
                    disabled={!selectedRuleId || isRunning}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg font-medium transition-all"
                  >
                    {isRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                    Run Backtest
                  </button>

                  <button
                    onClick={handleRetune}
                    disabled={tuningLoading || tuningStatus?.running}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg font-medium transition-all"
                  >
                    {tuningLoading || tuningStatus?.running ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <TrendingUp className="w-4 h-4" />
                    )}
                    {tuningStatus?.running ? "Retuning Rules..." : "Retune Rules (Auto-Apply)"}
                  </button>

                  {tuningStatus?.logTail ? (
                    <button
                      onClick={() => setTuningModalOpen(true)}
                      className="w-full px-4 py-2 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-800 rounded-lg transition-colors"
                    >
                      View Retune Log
                    </button>
                  ) : null}
                </div>
              </div>
            </div>

            <div className="p-4 bg-yellow-900/10 border border-yellow-900/20 rounded-xl flex gap-3">
              <AlertCircle className="w-5 h-5 text-yellow-500 shrink-0" />
              <p className="text-xs text-yellow-200/60 leading-relaxed">
                Make sure you have downloaded the historical data for the selected symbol and timeframe before running the test.
              </p>
            </div>
          </div>

          {/* Results Area */}
          <div className="lg:col-span-3">
            {!results && !isRunning ? (
              <div className="h-full min-h-[400px] flex flex-col items-center justify-center border-2 border-dashed border-zinc-800 rounded-2xl bg-zinc-900/20">
                <BarChart2 className="w-12 h-12 text-zinc-800 mb-4" />
                <p className="text-zinc-500">Select a rule and run a backtest to see results</p>
              </div>
            ) : isRunning ? (
              <div className="h-full min-h-[400px] flex flex-col items-center justify-center bg-zinc-900/20 rounded-2xl">
                <Loader2 className="w-12 h-12 text-blue-500 animate-spin mb-4" />
                <p className="text-zinc-400 font-medium">Processing historical candles...</p>
                <p className="text-zinc-600 text-sm">This may take a few seconds</p>
              </div>
            ) : results?.error ? (
              <div className="card border-red-900/50 bg-red-900/5">
                <div className="flex items-center gap-3 text-red-400 mb-2">
                  <AlertCircle className="w-5 h-5" />
                  <h3 className="font-bold">Backtest Failed</h3>
                </div>
                <p className="text-red-300/70">{results.error}</p>
                <button 
                  onClick={handleDownload}
                  className="mt-4 px-4 py-2 bg-red-900/20 hover:bg-red-900/30 text-red-400 rounded-lg text-sm transition-colors"
                >
                  Download Missing Data
                </button>
              </div>
            ) : (
                <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4">
                {(() => {
                  const equityCurve = Array.isArray(results?.equityCurve)
                    ? results.equityCurve
                    : [];
                  const trades = Array.isArray(results?.trades)
                    ? results.trades
                    : [];
                  const initialBalance = results?.initialBalance ?? 0;
                  const finalBalance = results?.finalBalance ?? 0;
                  return (
                  <>
                {/* Stats Summary */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="card">
                    <p className="text-xs text-zinc-500 uppercase font-bold mb-1">Total Return</p>
                    <p className={cn(
                      "text-2xl font-bold font-mono",
                      finalBalance >= initialBalance ? "text-green-400" : "text-red-400"
                    )}>
                      {initialBalance > 0
                        ? formatPercent(((finalBalance - initialBalance) / initialBalance) * 100)
                        : "0.00%"}
                    </p>
                  </div>
                  <div className="card">
                    <p className="text-xs text-zinc-500 uppercase font-bold mb-1">Final Balance</p>
                    <p className="text-2xl font-bold font-mono text-zinc-100">
                      ${formatNumber(finalBalance)}
                    </p>
                  </div>
                  <div className="card">
                    <p className="text-xs text-zinc-500 uppercase font-bold mb-1">Win Rate</p>
                    <p className="text-2xl font-bold font-mono text-blue-400">
                      {results.winRate}%
                    </p>
                  </div>
                  <div className="card">
                    <p className="text-xs text-zinc-500 uppercase font-bold mb-1">Total Trades</p>
                    <p className="text-2xl font-bold font-mono text-zinc-100">
                      {results.totalTrades}
                    </p>
                  </div>
                </div>

                {/* Equity Curve (Placeholder for now) */}
                <div className="card h-[300px] flex items-center justify-center bg-zinc-900/50 relative overflow-hidden">
                   <div className="absolute inset-0 flex items-end px-2 opacity-20">
                     {equityCurve.map((point: any, i: number) => (
                       <div 
                        key={i} 
                        className="flex-1 bg-blue-500" 
                        style={{
                          height: finalBalance > 0
                            ? `${(point.equity / finalBalance) * 100}%`
                            : "0%",
                        }}
                       />
                     ))}
                   </div>
                   <div className="relative z-10 text-center">
                      <BarChart2 className="w-8 h-8 text-zinc-700 mx-auto mb-2" />
                      <p className="text-sm text-zinc-500">Equity Curve Visualization</p>
                   </div>
                </div>

                {/* Trades List */}
                <div className="card">
                  <h3 className="font-bold text-zinc-200 mb-4">Trade History</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm min-w-[720px]">
                      <thead className="text-zinc-500 border-b border-zinc-800">
                        <tr>
                          <th className="pb-3 pl-2">Time</th>
                          <th className="pb-3">Side</th>
                          <th className="pb-3">Entry</th>
                          <th className="pb-3">Exit</th>
                          <th className="pb-3">P&L %</th>
                          <th className="pb-3 pr-2 text-right">Reason</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800/50">
                        {trades.map((trade: any, i: number) => (
                          <tr
                            key={i}
                            className="hover:bg-zinc-800/20 transition-colors cursor-pointer"
                            onClick={() => setSelectedTrade(trade)}
                          >
                            <td className="py-3 pl-2 text-zinc-400 font-mono">
                              {formatBacktestDate(trade.entryTime)}
                            </td>
                            <td className="py-3">
                              <span className={cn(
                                "px-2 py-0.5 rounded text-[10px] font-bold uppercase",
                                trade.side === "buy" ? "bg-green-500/10 text-green-500" : "bg-red-500/10 text-red-500"
                              )}>
                                {trade.side}
                              </span>
                            </td>
                            <td className="py-3 font-mono">${formatNumber(trade.entryPrice)}</td>
                            <td className="py-3 font-mono">
                              {trade.exitPrice ? `$${formatNumber(trade.exitPrice)}` : "—"}
                            </td>
                            <td className={cn(
                              "py-3 font-mono font-bold",
                              trade.pnl >= 0 ? "text-green-400" : "text-red-400"
                            )}>
                              {trade.pnl >= 0 ? "+" : ""}{formatNumber(trade.pnlPct ?? 0, 2)}%
                            </td>
                            <td className="py-3 pr-2 text-right text-zinc-500 text-xs">
                              {trade.reason}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                </>
                  );
                })()}
              </div>
            )}
          </div>
        </div>
      </main>

      <Modal
        isOpen={tuningModalOpen}
        onClose={() => setTuningModalOpen(false)}
        title="Retune Log"
        size="lg"
      >
        <div className="space-y-3">
          <div className="text-xs text-zinc-400">
            {tuningStatus?.running ? "Status: Running" : "Status: Idle"}
          </div>
          <pre className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-3 text-xs text-zinc-200 whitespace-pre-wrap max-h-[60vh] overflow-auto">
            {tuningStatus?.logTail || "No log output yet."}
          </pre>
        </div>
      </Modal>

      <Modal
        isOpen={!!selectedTrade}
        onClose={() => setSelectedTrade(null)}
        title="Backtest Trade Details"
      >
        {selectedTrade && (
          <div className="space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-zinc-500">Entry Time</p>
                <p className="text-zinc-100 font-mono">
                  {formatBacktestDate(selectedTrade.entryTime)}
                </p>
              </div>
              <div>
                <p className="text-zinc-500">Exit Time</p>
                <p className="text-zinc-100 font-mono">
                  {formatBacktestDate(selectedTrade.exitTime)}
                </p>
              </div>
              <div>
                <p className="text-zinc-500">Side</p>
                <p className="text-zinc-100 uppercase">{selectedTrade.side}</p>
              </div>
              <div>
                <p className="text-zinc-500">Amount</p>
                <p className="text-zinc-100 font-mono">
                  {formatNumber(selectedTrade.amount, 6)}
                </p>
              </div>
              <div>
                <p className="text-zinc-500">Entry Price</p>
                <p className="text-zinc-100 font-mono">
                  ${formatNumber(selectedTrade.entryPrice)}
                </p>
              </div>
              <div>
                <p className="text-zinc-500">Exit Price</p>
                <p className="text-zinc-100 font-mono">
                  {selectedTrade.exitPrice ? `$${formatNumber(selectedTrade.exitPrice)}` : "—"}
                </p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-zinc-500">P/L</p>
                <p className={cn(
                  "font-mono",
                  selectedTrade.pnl >= 0 ? "text-green-400" : "text-red-400"
                )}>
                  {selectedTrade.pnl >= 0 ? "+" : ""}{formatNumber(selectedTrade.pnl, 2)}
                </p>
              </div>
              <div>
                <p className="text-zinc-500">P/L %</p>
                <p className={cn(
                  "font-mono",
                  selectedTrade.pnlPct >= 0 ? "text-green-400" : "text-red-400"
                )}>
                  {selectedTrade.pnlPct >= 0 ? "+" : ""}{formatNumber(selectedTrade.pnlPct, 2)}%
                </p>
              </div>
            </div>
            <div>
              <p className="text-zinc-500">Reason</p>
              <p className="text-zinc-100">{selectedTrade.reason || "—"}</p>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
