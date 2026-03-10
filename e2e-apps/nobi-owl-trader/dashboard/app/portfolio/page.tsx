"use client";

import { useEffect, useState } from "react";
import { Navigation } from "@/components/Navigation";
import { useTradingStore } from "@/lib/store";
import { cn, formatNumber, formatCurrency, formatPercent } from "@/lib/utils";
import { Modal } from "@/components/Modal";
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Target,
  Shield,
  Activity,
  BarChart3,
  AlertTriangle,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

// Constants
const PORTFOLIO_HISTORY_DAYS = 30;
const AUTO_REFRESH_INTERVAL = 10000; // 10 seconds

// ===========================
// Portfolio Summary Cards
// ===========================

function PortfolioSummary() {
  const { portfolio, isLoading } = useTradingStore();
  const loading = isLoading.portfolio;

  const stats = [
    {
      label: "Total Portfolio Value",
      value: portfolio ? formatCurrency(portfolio.totalValue) : "—",
      icon: Wallet,
      color: "text-blue-400",
    },
    {
      label: "Cash Balance",
      value: portfolio ? formatCurrency(portfolio.cash) : "—",
      icon: DollarSign,
      color: "text-green-400",
    },
    {
      label: "Unrealized P&L",
      value: portfolio ? formatCurrency(portfolio.unrealizedPnl) : "—",
      positive: portfolio ? portfolio.unrealizedPnl >= 0 : null,
      icon: TrendingUp,
    },
    {
      label: "Realized P&L Today",
      value: portfolio ? formatCurrency(portfolio.realizedPnl) : "—",
      positive: portfolio ? portfolio.realizedPnl >= 0 : null,
      icon: Target,
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {stats.map((stat) => {
        const Icon = stat.icon;
        return (
          <div
            key={stat.label}
            className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 transition-all hover:border-zinc-700"
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
                    : stat.color || "text-zinc-500"
                )}
              />
            </div>
            {loading ? (
              <div className="h-7 bg-zinc-800 rounded animate-pulse" />
            ) : (
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
            )}
          </div>
        );
      })}
    </div>
  );
}

// ===========================
// Open Positions Table
// ===========================

function OpenPositions() {
  const { positions, isLoading } = useTradingStore();
  const loading = isLoading.positions;
  const [selectedPosition, setSelectedPosition] = useState<any | null>(null);

  return (
    <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-6 mb-6">
      <div className="flex items-center gap-3 mb-4">
        <Activity className="w-5 h-5 text-zinc-400" />
        <h2 className="text-lg font-bold text-zinc-100">Open Positions</h2>
        <span className="text-sm text-zinc-500">
          ({positions.length} active)
        </span>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-12 bg-zinc-800 rounded animate-pulse" />
          ))}
        </div>
      ) : positions.length === 0 ? (
        <div className="py-12 text-center text-zinc-500">
          <Activity className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p>No open positions</p>
          <p className="text-sm mt-1">Your positions will appear here</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px]">
            <thead>
              <tr className="text-left text-zinc-500 text-sm border-b border-zinc-800">
                <th className="pb-3 font-medium">Symbol</th>
                <th className="pb-3 font-medium text-right">Amount</th>
                <th className="pb-3 font-medium text-right">Avg Cost</th>
                <th className="pb-3 font-medium text-right">Current Price</th>
                <th className="pb-3 font-medium text-right">Market Value</th>
                <th className="pb-3 font-medium text-right">Unrealized P&L</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {positions.map((position) => (
                <tr
                  key={position.symbol}
                  className="text-zinc-300 cursor-pointer hover:bg-zinc-900/50 transition-colors"
                  onClick={() => setSelectedPosition(position)}
                >
                  <td className="py-3 font-medium">{position.symbol}</td>
                  <td className="py-3 text-right font-mono">
                    {formatNumber(position.quantity, 6)}
                  </td>
                  <td className="py-3 text-right font-mono">
                    {formatCurrency(position.avgCost)}
                  </td>
                  <td className="py-3 text-right font-mono">
                    {formatCurrency(position.currentPrice)}
                  </td>
                  <td className="py-3 text-right font-mono">
                    {formatCurrency(position.marketValue)}
                  </td>
                  <td className="py-3 text-right">
                    <div className="flex flex-col items-end">
                      <span
                        className={cn(
                          "font-mono font-bold",
                          position.unrealizedPnl >= 0
                            ? "text-green-400"
                            : "text-red-400"
                        )}
                      >
                        {formatCurrency(position.unrealizedPnl)}
                      </span>
                      <span
                        className={cn(
                          "text-xs font-mono",
                          position.unrealizedPnl >= 0
                            ? "text-green-400/70"
                            : "text-red-400/70"
                        )}
                      >
                        {formatPercent(position.unrealizedPnlPercent / 100)}
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal
        isOpen={!!selectedPosition}
        onClose={() => setSelectedPosition(null)}
        title={selectedPosition ? `Position Details • ${selectedPosition.symbol}` : "Position Details"}
      >
        {selectedPosition && (
          <div className="space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-zinc-500">Symbol</p>
                <p className="text-zinc-100 font-mono">{selectedPosition.symbol}</p>
              </div>
              <div>
                <p className="text-zinc-500">Quantity</p>
                <p className="text-zinc-100 font-mono">{formatNumber(selectedPosition.quantity, 6)}</p>
              </div>
              <div>
                <p className="text-zinc-500">Avg Cost</p>
                <p className="text-zinc-100 font-mono">{formatCurrency(selectedPosition.avgCost)}</p>
              </div>
              <div>
                <p className="text-zinc-500">Current Price</p>
                <p className="text-zinc-100 font-mono">{formatCurrency(selectedPosition.currentPrice)}</p>
              </div>
              <div>
                <p className="text-zinc-500">Market Value</p>
                <p className="text-zinc-100 font-mono">{formatCurrency(selectedPosition.marketValue)}</p>
              </div>
              <div>
                <p className="text-zinc-500">Unrealized P/L</p>
                <p className={cn(
                  "font-mono",
                  selectedPosition.unrealizedPnl >= 0 ? "text-green-400" : "text-red-400"
                )}>
                  {formatCurrency(selectedPosition.unrealizedPnl)}
                </p>
              </div>
              <div>
                <p className="text-zinc-500">Unrealized P/L %</p>
                <p className={cn(
                  "font-mono",
                  selectedPosition.unrealizedPnlPercent >= 0 ? "text-green-400" : "text-red-400"
                )}>
                  {formatPercent(selectedPosition.unrealizedPnlPercent / 100)}
                </p>
              </div>
              <div>
                <p className="text-zinc-500">Opened</p>
                <p className="text-zinc-100 font-mono">
                  {new Date(selectedPosition.firstBuyDate).toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-zinc-500">Last Updated</p>
                <p className="text-zinc-100 font-mono">
                  {new Date(selectedPosition.lastBuyDate).toLocaleString()}
                </p>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

// ===========================
// Performance Metrics Cards
// ===========================

function PerformanceMetrics() {
  const { metrics, isLoading } = useTradingStore();
  const loading = isLoading.metrics;

  const metricCards = [
    {
      label: "Win Rate",
      value: metrics ? formatPercent(metrics.winRate / 100) : "—",
      subtitle: metrics
        ? `${metrics.winningTrades}W / ${metrics.losingTrades}L`
        : "—",
      positive: metrics ? metrics.winRate >= 50 : null,
    },
    {
      label: "Profit Factor",
      value: metrics ? formatNumber(metrics.profitFactor, 2) : "—",
      subtitle: "Win/Loss Ratio",
      positive: metrics ? metrics.profitFactor >= 1 : null,
    },
    {
      label: "Avg Win / Loss",
      value: metrics
        ? `${formatCurrency(metrics.avgWin, 0)} / ${formatCurrency(Math.abs(metrics.avgLoss), 0)}`
        : "—",
      subtitle: "Per Trade",
      positive: metrics ? metrics.avgWin > Math.abs(metrics.avgLoss) : null,
    },
    {
      label: "Sharpe Ratio",
      value: metrics ? formatNumber(metrics.sharpeRatio, 2) : "—",
      subtitle: "Risk-Adjusted Return",
      positive: metrics ? metrics.sharpeRatio >= 1 : null,
    },
    {
      label: "Max Drawdown",
      value: metrics ? formatPercent(metrics.maxDrawdownPercent / 100) : "—",
      subtitle: formatCurrency(metrics?.maxDrawdown || 0),
      positive: false,
    },
    {
      label: "Total Trades",
      value: metrics ? formatNumber(metrics.totalTrades, 0) : "—",
      subtitle: `Avg Hold: ${metrics ? formatNumber(metrics.avgHoldingPeriod, 0) : "—"}h`,
      positive: null,
    },
  ];

  return (
    <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-6 mb-6">
      <div className="flex items-center gap-3 mb-4">
        <BarChart3 className="w-5 h-5 text-zinc-400" />
        <h2 className="text-lg font-bold text-zinc-100">Performance Metrics</h2>
      </div>

      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-20 bg-zinc-800 rounded animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {metricCards.map((metric) => (
            <div
              key={metric.label}
              className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-4"
            >
              <p className="text-zinc-500 text-xs mb-1">{metric.label}</p>
              <p
                className={cn(
                  "text-lg font-bold font-mono",
                  metric.positive === true
                    ? "text-green-400"
                    : metric.positive === false
                    ? "text-red-400"
                    : "text-zinc-100"
                )}
              >
                {metric.value}
              </p>
              <p className="text-zinc-600 text-xs mt-1">{metric.subtitle}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ===========================
// P&L History Chart
// ===========================

function PnLChart() {
  const { portfolioHistory, isLoading } = useTradingStore();
  const loading = isLoading.history;

  // Format data for recharts
  const chartData = portfolioHistory.map((snapshot) => ({
    date: new Date(snapshot.timestamp * 1000).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    }),
    value: snapshot.totalValue,
    pnl: snapshot.totalPnl,
  }));

  // Calculate overall trend
  const isPositiveTrend =
    chartData.length > 0
      ? chartData[chartData.length - 1].value > chartData[0].value
      : true;

  return (
    <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <TrendingUp className="w-5 h-5 text-zinc-400" />
          <h2 className="text-lg font-bold text-zinc-100">
            Portfolio Value (30 Days)
          </h2>
        </div>
        {chartData.length > 0 && (
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "text-sm font-mono",
                isPositiveTrend ? "text-green-400" : "text-red-400"
              )}
            >
              {isPositiveTrend ? "+" : ""}
              {formatPercent(
                (chartData[chartData.length - 1].value - chartData[0].value) /
                  chartData[0].value
              )}
            </span>
          </div>
        )}
      </div>

      {loading ? (
        <div className="h-64 bg-zinc-800 rounded animate-pulse" />
      ) : chartData.length === 0 ? (
        <div className="h-64 flex flex-col items-center justify-center text-zinc-500">
          <TrendingUp className="w-12 h-12 mb-3 opacity-50" />
          <p>No history data yet</p>
          <p className="text-sm mt-1">Portfolio snapshots will appear here</p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
            <XAxis
              dataKey="date"
              stroke="#71717a"
              style={{ fontSize: "12px" }}
            />
            <YAxis
              stroke="#71717a"
              style={{ fontSize: "12px" }}
              tickFormatter={(value) => `$${formatNumber(value, 0)}`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#18181b",
                border: "1px solid #27272a",
                borderRadius: "8px",
                color: "#fafafa",
              }}
              formatter={(value) => {
                const val = value as number;
                if (!val) return ["$0.00", ""];
                return [formatCurrency(val), "Portfolio Value"];
              }}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={isPositiveTrend ? "#4ade80" : "#f87171"}
              strokeWidth={2}
              dot={false}
              animationDuration={1000}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

// ===========================
// Risk Status Indicator
// ===========================

function RiskStatus() {
  const { riskLimits, portfolio, metrics } = useTradingStore();

  // Calculate risk levels (with division by zero protection)
  const dailyLossPercent = portfolio && riskLimits.maxDailyLoss > 0
    ? Math.abs(portfolio.realizedPnl / riskLimits.maxDailyLoss)
    : 0;
  const drawdownPercent = metrics && riskLimits.maxDrawdownPercent > 0
    ? Math.abs(metrics.maxDrawdownPercent / riskLimits.maxDrawdownPercent)
    : 0;

  // Determine overall risk level
  const maxRiskPercent = Math.max(dailyLossPercent, drawdownPercent);
  const riskLevel =
    maxRiskPercent >= 0.8 ? "danger" : maxRiskPercent >= 0.5 ? "warning" : "safe";

  const riskColor =
    riskLevel === "danger"
      ? "text-red-400"
      : riskLevel === "warning"
      ? "text-yellow-400"
      : "text-green-400";

  const riskBg =
    riskLevel === "danger"
      ? "bg-red-400/10 border-red-400/20"
      : riskLevel === "warning"
      ? "bg-yellow-400/10 border-yellow-400/20"
      : "bg-green-400/10 border-green-400/20";

  const canTrade = maxRiskPercent < 1.0;

  return (
    <div
      className={cn(
        "border rounded-xl p-6 transition-all",
        riskBg
      )}
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <Shield className={cn("w-5 h-5", riskColor)} />
          <h2 className="text-lg font-bold text-zinc-100">Risk Status</h2>
        </div>
        <div
          className={cn(
            "px-3 py-1 rounded-full text-xs font-medium uppercase",
            riskColor
          )}
        >
          {riskLevel}
        </div>
      </div>

      <div className="space-y-4">
        {/* Daily Loss Limit */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-zinc-400">Daily Loss Limit</span>
            <span className={cn("text-sm font-mono font-bold", riskColor)}>
              {formatPercent(dailyLossPercent)}
            </span>
          </div>
          <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className={cn(
                "h-full transition-all duration-500",
                riskLevel === "danger"
                  ? "bg-red-400"
                  : riskLevel === "warning"
                  ? "bg-yellow-400"
                  : "bg-green-400"
              )}
              style={{ width: `${Math.max(0, Math.min(dailyLossPercent * 100, 100))}%` }}
            />
          </div>
          <div className="flex items-center justify-between mt-1">
            <span className="text-xs text-zinc-600">
              {formatCurrency(Math.abs(portfolio?.realizedPnl || 0))} /{" "}
              {formatCurrency(riskLimits.maxDailyLoss)}
            </span>
          </div>
        </div>

        {/* Max Drawdown */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-zinc-400">Max Drawdown</span>
            <span className={cn("text-sm font-mono font-bold", riskColor)}>
              {formatPercent(drawdownPercent)}
            </span>
          </div>
          <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className={cn(
                "h-full transition-all duration-500",
                riskLevel === "danger"
                  ? "bg-red-400"
                  : riskLevel === "warning"
                  ? "bg-yellow-400"
                  : "bg-green-400"
              )}
              style={{ width: `${Math.max(0, Math.min(drawdownPercent * 100, 100))}%` }}
            />
          </div>
          <div className="flex items-center justify-between mt-1">
            <span className="text-xs text-zinc-600">
              {formatPercent((metrics?.maxDrawdownPercent || 0) / 100)} /{" "}
              {formatPercent(riskLimits.maxDrawdownPercent / 100)}
            </span>
          </div>
        </div>

        {/* Trading Status */}
        <div
          className={cn(
            "flex items-center gap-2 p-3 rounded-lg",
            canTrade
              ? "bg-green-400/5 border border-green-400/20"
              : "bg-red-400/5 border border-red-400/20"
          )}
        >
          {canTrade ? (
            <>
              <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
              <span className="text-sm text-green-400 font-medium">
                Trading Enabled
              </span>
            </>
          ) : (
            <>
              <AlertTriangle className="w-4 h-4 text-red-400" />
              <span className="text-sm text-red-400 font-medium">
                Trading Disabled - Risk Limit Reached
              </span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ===========================
// Main Portfolio Page
// ===========================

export default function PortfolioPage() {
  const {
    fetchPortfolio,
    fetchPositions,
    fetchMetrics,
    fetchPortfolioHistory,
    fetchRiskLimits,
  } = useTradingStore();

  // Fetch all data on mount
  useEffect(() => {
    fetchPortfolio();
    fetchPositions();
    fetchMetrics();
    fetchPortfolioHistory(PORTFOLIO_HISTORY_DAYS);
    fetchRiskLimits();
  }, [fetchPortfolio, fetchPositions, fetchMetrics, fetchPortfolioHistory, fetchRiskLimits]);

  // Auto-refresh
  useEffect(() => {
    const interval = setInterval(() => {
      fetchPortfolio();
      fetchPositions();
      fetchMetrics();
    }, AUTO_REFRESH_INTERVAL);

    return () => clearInterval(interval);
  }, [fetchPortfolio, fetchPositions, fetchMetrics]);

  return (
    <div className="min-h-screen bg-zinc-950">
      <Navigation />

      <main className="max-w-7xl mx-auto px-4 py-8">
        {/* Page Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-zinc-800 rounded-xl flex items-center justify-center">
              <Wallet className="w-6 h-6 text-zinc-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-zinc-100">Portfolio</h1>
              <p className="text-zinc-500">P&L analytics and risk management</p>
            </div>
          </div>
        </div>

        {/* Portfolio Summary Cards */}
        <PortfolioSummary />

        {/* Main Grid Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column - Charts and Tables */}
          <div className="lg:col-span-2 space-y-6">
            {/* P&L History Chart */}
            <PnLChart />

            {/* Open Positions Table */}
            <OpenPositions />

            {/* Performance Metrics */}
            <PerformanceMetrics />
          </div>

          {/* Right Column - Risk Status */}
          <div className="lg:col-span-1">
            <RiskStatus />
          </div>
        </div>

        {/* Footer */}
        <footer className="mt-8 pt-4 border-t border-zinc-800">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4 text-xs text-zinc-600">
            <p>
              Portfolio data refreshes automatically every 10 seconds
            </p>
            <p>
              All P&L calculations include realized and unrealized gains/losses
            </p>
          </div>
        </footer>
      </main>
    </div>
  );
}
