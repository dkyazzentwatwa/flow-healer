/**
 * Zustand State Management Store for NobiBot Dashboard
 * Central state management with API integration and persistence
 */

import { useEffect } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import {
  Ticker,
  ScanResult,
  Trade,
  Position,
  Portfolio,
  PerformanceMetrics,
  RiskLimits,
  RiskExposure,
  PortfolioSnapshot,
  UserSettings,
  HistoricalData,
  Balance,
  OrderResponse,
  AutomationRule,
  LogEntry,
  TuningStatus,
} from "./types";
import { snakeToCamel } from "./utils";

// ===========================
// API Configuration
// ===========================

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getApiBaseUrl(): string {
  if (typeof window === "undefined") {
    return API_BASE_URL;
  }

  try {
    const raw = localStorage.getItem("nobibot-storage");
    if (raw) {
      const parsed = JSON.parse(raw);
      const apiUrl = parsed?.state?.settings?.apiUrl;
      if (apiUrl) {
        return apiUrl;
      }
    }
  } catch {
    // Ignore storage errors and fall back to env/default
  }

  return API_BASE_URL;
}

/**
 * Generic API fetch wrapper with error handling
 */
async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T | null> {
  try {
    const baseUrl = getApiBaseUrl();
    const response = await fetch(`${baseUrl}${endpoint}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: response.statusText }));
      const message = error.message || error.detail || response.statusText;
      throw new Error(message || `HTTP ${response.status}`);
    }

    const data = await response.json();
    // Convert snake_case to camelCase for all API responses
    return snakeToCamel<T>(data);
  } catch (error) {
    console.error(`API Error (${endpoint}):`, error);
    throw error;
  }
}

// ===========================
// Store State Interface
// ===========================

interface TradingState {
  // Connection Status
  isConnected: boolean;
  exchange: string;
  isPaperTrading: boolean;
  lastUpdate: number;
  error: string | null;

  // Market Data
  selectedSymbol: string;
  selectedTimeframe: string;
  ticker: Ticker | null;
  scanResult: ScanResult | null;
  historicalData: HistoricalData | null;

  // Portfolio & Positions
  portfolio: Portfolio | null;
  balance: Balance | null;
  positions: Position[];
  portfolioHistory: PortfolioSnapshot[];
  metrics: PerformanceMetrics | null;

  // Risk Management
  riskLimits: RiskLimits;
  riskExposure: RiskExposure | null;

  // Trades
  recentTrades: Trade[];
  allTrades: Trade[];

  // History
  tradeHistory: Trade[];
  scanHistory: ScanResult[];

  // User Settings
  settings: UserSettings;

  // Automation Rules
  automationRules: AutomationRule[];

  // Logs
  logs: LogEntry[];

  // Loading States
  isLoading: {
    ticker: boolean;
    scan: boolean;
    portfolio: boolean;
    positions: boolean;
    trades: boolean;
    metrics: boolean;
    history: boolean;
    automation: boolean;
    logs: boolean;
  };

  // ===========================
  // Actions - Connection
  // ===========================

  checkConnection: () => Promise<void>;
  setConnected: (connected: boolean) => void;
  setError: (error: string | null) => void;
  clearError: () => void;

  // ===========================
  // Actions - Market Data
  // ===========================

  setSymbol: (symbol: string) => void;
  setSelectedSymbol: (symbol: string) => void;
  setSelectedTimeframe: (timeframe: string) => void;
  fetchTicker: () => Promise<void>;
  fetchScan: () => Promise<void>;
  runScan: () => Promise<void>;
  fetchHistoricalData: (symbol: string, interval: string, limit?: number) => Promise<void>;

  // ===========================
  // Actions - Portfolio
  // ===========================

  fetchPortfolio: () => Promise<void>;
  fetchPositions: () => Promise<void>;
  fetchMetrics: () => Promise<void>;
  fetchPortfolioHistory: (days?: number) => Promise<void>;
  fetchBalance: () => Promise<void>;

  // ===========================
  // Actions - Trading
  // ===========================

  fetchRecentTrades: (limit?: number) => Promise<void>;
  fetchAllTrades: () => Promise<void>;
  executeTrade: (
    symbol: string,
    side: "BUY" | "SELL",
    quantity: number,
    type?: "MARKET" | "LIMIT",
    price?: number
  ) => Promise<Trade | null>;
  placeTrade: (side: "buy" | "sell", amount: number) => Promise<Trade>;

  // ===========================
  // Actions - Risk Management
  // ===========================

  fetchRiskLimits: () => Promise<void>;
  fetchRiskExposure: () => Promise<void>;
  updateRiskLimits: (limits: Partial<RiskLimits>) => Promise<void>;

  // ===========================
  // Actions - Settings
  // ===========================

  updateSettings: (settings: Partial<UserSettings>) => void;
  resetSettings: () => void;

  // ===========================
  // Actions - Automation
  // ===========================

  fetchAutomationRules: () => Promise<void>;
  createAutomationRule: (rule: Omit<AutomationRule, "id" | "isActive" | "lastTriggered">) => Promise<void>;
  updateAutomationRule: (id: string, updates: Partial<AutomationRule>) => Promise<void>;
  deleteAutomationRule: (id: string) => Promise<void>;
  toggleAutomationRule: (id: string, isActive: boolean) => Promise<void>;
  setPaperBalance: (currency: string, amount: number) => Promise<void>;
  resetPaperAccount: (startBalance?: number) => Promise<void>;

  // ===========================
  // Actions - Logs
  // ===========================

  fetchLogs: (limit?: number, level?: string) => Promise<void>;
  clearLogs: (days?: number) => Promise<void>;

  // ===========================
  // Actions - Backtest
  // ===========================

  runBacktest: (ruleId: string, days: number, balance: number, exitRuleId?: string) => Promise<any>;
  downloadBacktestData: (symbol: string, timeframe: string, days: number) => Promise<void>;
  runTuning: (options?: {
    autoApply?: boolean;
    allSymbols?: boolean;
    skipDownload?: boolean;
    fast?: boolean;
    focusSymbols?: string;
  }) => Promise<TuningStatus | null>;
  fetchTuningStatus: () => Promise<TuningStatus | null>;

  // ===========================
  // Actions - History
  // ===========================

  loadHistory: () => void;
  clearTradeHistory: () => void;
  clearScanHistory: () => void;

  // ===========================
  // Actions - Utilities
  // ===========================

  refreshAll: () => Promise<void>;
  reset: () => void;
}

// ===========================
// Default Values
// ===========================

const defaultRiskLimits: RiskLimits = {
  maxDailyLoss: 500,
  maxDrawdownPercent: 20,
  maxPositionSizePercent: 20,
  maxExposurePercent: 80,
  stopLossPercent: 5,
  takeProfitPercent: 10,
  trailingStopPercent: 3,
};

const defaultSettings: UserSettings = {
  theme: "dark",
  currency: "USD",
  defaultSymbol: "BTC/USDT",
  refreshInterval: 10000,
  enableNotifications: true,
  enableAutoRefresh: true,
  chartType: "candlestick",
  timeframe: "1h",
  apiUrl: API_BASE_URL,
  riskLimits: defaultRiskLimits,
};

const defaultLoadingState = {
  ticker: false,
  scan: false,
  portfolio: false,
  positions: false,
  trades: false,
  metrics: false,
  history: false,
  automation: false,
  logs: false,
};

// ===========================
// Zustand Store
// ===========================

export const useTradingStore = create<TradingState>()(
  persist(
    (set, get) => ({
      // Initial State
      isConnected: false,
      exchange: "binanceus",
      isPaperTrading: true,
      lastUpdate: Date.now(),
      error: null,

      selectedSymbol: "BTC/USDT",
      selectedTimeframe: "1h",
      ticker: null,
      scanResult: null,
      historicalData: null,

      portfolio: null,
      balance: null,
      positions: [],
      portfolioHistory: [],
      metrics: null,

      riskLimits: defaultRiskLimits,
      riskExposure: null,

      recentTrades: [],
      allTrades: [],

      tradeHistory: [],
      scanHistory: [],

      settings: defaultSettings,
      automationRules: [],
      logs: [],

      isLoading: {
        ...defaultLoadingState,
        logs: false,
      },

      // ===========================
      // Connection Actions
      // ===========================

      checkConnection: async () => {
        try {
          const { settings } = get();
          const response = await fetch(`${settings.apiUrl}/health`, {
            method: "GET",
            signal: AbortSignal.timeout(5000), // 5 second timeout
          });

          if (response.ok) {
            const data = await response.json();
            set({
              isConnected: true,
              exchange: data.exchange || "binanceus",
              isPaperTrading: data.paper_trading ?? true,
              error: null,
              lastUpdate: Date.now(),
            });
            get().fetchRiskLimits();
          } else {
            set({
              isConnected: false,
              error: `API returned ${response.status}`,
              lastUpdate: Date.now(),
            });
          }
        } catch (err) {
          set({
            isConnected: false,
            error: err instanceof Error ? err.message : "Connection failed",
            lastUpdate: Date.now(),
          });
        }
      },

      setConnected: (connected) => {
        set({ isConnected: connected, lastUpdate: Date.now() });
      },

      setError: (error) => {
        set({ error, lastUpdate: Date.now() });
      },

      clearError: () => {
        set({ error: null });
      },

      // ===========================
      // Market Data Actions
      // ===========================

      setSymbol: (symbol) => {
        set({ selectedSymbol: symbol });
        // Auto-fetch data for new symbol
        get().fetchTicker();
        get().fetchScan();
      },

      setSelectedSymbol: (symbol) => {
        get().setSymbol(symbol);
      },

      setSelectedTimeframe: (timeframe) => {
        set({ selectedTimeframe: timeframe });
        get().runScan();
      },

      runScan: async () => {
        await get().fetchScan();
      },

      fetchTicker: async () => {
        const { selectedSymbol } = get();
        set((state) => ({ isLoading: { ...state.isLoading, ticker: true } }));

        try {
          const data = await fetchAPI<{ ticker: Ticker }>(
            `/api/market/ticker?symbol=${encodeURIComponent(selectedSymbol)}`
          );
          if (data?.ticker) {
            set({
              ticker: data.ticker,
              lastUpdate: Date.now(),
              error: null,
            });
          }
        } catch (error) {
          set({ error: (error as Error).message });
        } finally {
          set((state) => ({ isLoading: { ...state.isLoading, ticker: false } }));
        }
      },

      fetchScan: async () => {
        const { selectedSymbol, selectedTimeframe } = get();
        set((state) => ({ isLoading: { ...state.isLoading, scan: true } }));

        try {
          const data = await fetchAPI<ScanResult>("/api/scan", {
            method: "POST",
            body: JSON.stringify({
              symbol: selectedSymbol,
              timeframe: selectedTimeframe,
            }),
          });
          if (data) {
            const normalizedScan: ScanResult = {
              ...data,
              timestamp:
                typeof data.timestamp === "string"
                  ? Date.parse(data.timestamp)
                  : data.timestamp,
            };

            let updatedHistory: ScanResult[] = [];
            try {
              const existing = localStorage.getItem("scan_history");
              updatedHistory = existing ? JSON.parse(existing) : [];
              updatedHistory.unshift(normalizedScan);
              updatedHistory = updatedHistory.slice(0, 50);
              localStorage.setItem(
                "scan_history",
                JSON.stringify(updatedHistory)
              );
            } catch {
              updatedHistory = [normalizedScan];
              localStorage.setItem(
                "scan_history",
                JSON.stringify(updatedHistory)
              );
            }

            set({
              scanResult: normalizedScan,
              scanHistory: updatedHistory.length > 0 ? updatedHistory : get().scanHistory,
              lastUpdate: Date.now(),
              error: null,
            });
          }
        } catch (error) {
          set({ error: (error as Error).message });
        } finally {
          set((state) => ({ isLoading: { ...state.isLoading, scan: false } }));
        }
      },

      fetchHistoricalData: async (symbol, interval, limit = 100) => {
        try {
          const data = await fetchAPI<HistoricalData>(
            `/api/market/history?symbol=${encodeURIComponent(
              symbol
            )}&interval=${encodeURIComponent(interval)}&limit=${limit}`
          );
          if (data) {
            set({ historicalData: data });
          }
        } catch (error) {
          set({ error: (error as Error).message });
        }
      },

      // ===========================
      // Portfolio Actions
      // ===========================

      fetchPortfolio: async () => {
        set((state) => ({ isLoading: { ...state.isLoading, portfolio: true } }));

        try {
          const data = await fetchAPI<{ portfolio: Portfolio }>(
            "/api/portfolio/summary"
          );
          if (data?.portfolio) {
            set({
              portfolio: data.portfolio,
              lastUpdate: Date.now(),
              error: null,
            });
          }
        } catch (error) {
          set({ error: (error as Error).message });
        } finally {
          set((state) => ({ isLoading: { ...state.isLoading, portfolio: false } }));
        }
      },

      fetchPositions: async () => {
        set((state) => ({ isLoading: { ...state.isLoading, positions: true } }));

        try {
          const data = await fetchAPI<{ positions: Position[] }>(
            "/api/portfolio/positions"
          );
          if (data?.positions) {
            set({
              positions: data.positions,
              lastUpdate: Date.now(),
              error: null,
            });
          }
        } catch (error) {
          set({ error: (error as Error).message });
        } finally {
          set((state) => ({ isLoading: { ...state.isLoading, positions: false } }));
        }
      },

      fetchMetrics: async () => {
        set((state) => ({ isLoading: { ...state.isLoading, metrics: true } }));

        try {
          const data = await fetchAPI<PerformanceMetrics>("/api/portfolio/metrics");
          if (data) {
            set({
              metrics: data,
              lastUpdate: Date.now(),
              error: null,
            });
          }
        } catch (error) {
          set({ error: (error as Error).message });
        } finally {
          set((state) => ({ isLoading: { ...state.isLoading, metrics: false } }));
        }
      },

      fetchPortfolioHistory: async (days = 30) => {
        set((state) => ({ isLoading: { ...state.isLoading, history: true } }));

        try {
          const data = await fetchAPI<{ history: PortfolioSnapshot[] }>(
            `/api/portfolio/history?days=${days}`
          );
          if (data?.history) {
            set({
              portfolioHistory: data.history,
              lastUpdate: Date.now(),
              error: null,
            });
          }
        } catch (error) {
          set({ error: (error as Error).message });
        } finally {
          set((state) => ({ isLoading: { ...state.isLoading, history: false } }));
        }
      },

      fetchBalance: async () => {
        set((state) => ({ isLoading: { ...state.isLoading, portfolio: true } }));
        try {
          const data = await fetchAPI<Balance>("/api/balance");
          if (data) {
            set({
              balance: data,
              lastUpdate: Date.now(),
              error: null,
            });
          }
        } catch (error) {
          set({ error: (error as Error).message });
        } finally {
          set((state) => ({ isLoading: { ...state.isLoading, portfolio: false } }));
        }
      },

      // ===========================
      // Trading Actions
      // ===========================

      fetchRecentTrades: async (limit = 10) => {
        set((state) => ({ isLoading: { ...state.isLoading, trades: true } }));

        try {
          const data = await fetchAPI<{ trades: Trade[] }>(
            `/api/portfolio/trades?limit=${limit}`
          );
          if (data?.trades) {
            set({
              recentTrades: data.trades,
              lastUpdate: Date.now(),
              error: null,
            });
          }
        } catch (error) {
          set({ error: (error as Error).message });
        } finally {
          set((state) => ({ isLoading: { ...state.isLoading, trades: false } }));
        }
      },

      fetchAllTrades: async () => {
        set((state) => ({ isLoading: { ...state.isLoading, trades: true } }));

        try {
          const data = await fetchAPI<{ trades: Trade[] }>("/api/portfolio/trades");
          if (data?.trades) {
            set({
              allTrades: data.trades,
              lastUpdate: Date.now(),
              error: null,
            });
          }
        } catch (error) {
          set({ error: (error as Error).message });
        } finally {
          set((state) => ({ isLoading: { ...state.isLoading, trades: false } }));
        }
      },

      executeTrade: async (symbol, side, quantity, type = "MARKET", price) => {
        try {
          const data = await fetchAPI<OrderResponse>("/api/trade", {
            method: "POST",
            body: JSON.stringify({
              symbol,
              side: side.toLowerCase(),
              amount: quantity,
              order_type: type.toLowerCase(),
              price,
            }),
          });

          if (!data) {
            return null;
          }

          const trade: Trade = {
            id: data.id,
            symbol: data.symbol,
            side: data.side as "buy" | "sell",
            amount: data.amount,
            price: data.price || 0,
            total: (data.price || 0) * data.amount,
            fee: 0,
            timestamp: Date.now(),
            status: data.status as "open" | "closed" | "cancelled",
            paper: data.paperTrade ?? false,
          };

          await Promise.all([
            get().fetchPortfolio(),
            get().fetchPositions(),
            get().fetchRecentTrades(),
            get().fetchBalance(),
          ]);

          return trade;
        } catch (error) {
          set({ error: (error as Error).message });
          return null;
        }
      },

      placeTrade: async (side, amount) => {
        const symbol = get().selectedSymbol;
        const trade = await get().executeTrade(
          symbol,
          side.toUpperCase() as "BUY" | "SELL",
          amount,
          "MARKET"
        );
        if (!trade) {
          throw new Error("Trade failed");
        }
        return trade;
      },

      // ===========================
      // Risk Management Actions
      // ===========================

      fetchRiskLimits: async () => {
        try {
          const data = await fetchAPI<RiskLimits>("/api/risk/limits");
          if (data) {
            set({
              riskLimits: data,
              settings: {
                ...get().settings,
                riskLimits: data,
              },
              lastUpdate: Date.now(),
              error: null,
            });
          }
        } catch (error) {
          set({ error: (error as Error).message });
        }
      },

      fetchRiskExposure: async () => {
        try {
          const data = await fetchAPI<RiskExposure>("/api/risk/check");
          if (data) {
            set({
              riskExposure: data,
              lastUpdate: Date.now(),
              error: null,
            });
          }
        } catch (error) {
          set({ error: (error as Error).message });
        }
      },

      updateRiskLimits: async (limits) => {
        try {
          const newLimits = { ...get().riskLimits, ...limits };
          const data = await fetchAPI<RiskLimits>("/api/risk/limits", {
            method: "POST",
            body: JSON.stringify(newLimits),
          });

          if (data) {
            set({
              riskLimits: data,
              settings: {
                ...get().settings,
                riskLimits: data,
              },
            });
          }
        } catch (error) {
          set({ error: (error as Error).message });
        }
      },

      // ===========================
      // Settings Actions
      // ===========================

      updateSettings: (newSettings) => {
        set((state) => ({
          settings: { ...state.settings, ...newSettings },
        }));
      },

      resetSettings: () => {
        set({ settings: defaultSettings });
      },

      // ===========================
      // Automation Actions
      // ===========================

      fetchAutomationRules: async () => {
        set((state) => ({ isLoading: { ...state.isLoading, automation: true } }));
        try {
          const rules = await fetchAPI<AutomationRule[]>("/api/automation/rules");
          if (rules) {
            set({ automationRules: rules });
          }
        } catch (error) {
          set({ error: (error as Error).message });
        } finally {
          set((state) => ({ isLoading: { ...state.isLoading, automation: false } }));
        }
      },

      createAutomationRule: async (rule) => {
        try {
          await fetchAPI<AutomationRule>("/api/automation/rules", {
            method: "POST",
            body: JSON.stringify(rule),
          });
          await get().fetchAutomationRules();
        } catch (error) {
          set({ error: (error as Error).message });
        }
      },

      updateAutomationRule: async (id, updates) => {
        try {
          await fetchAPI<AutomationRule>(`/api/automation/rules/${id}`, {
            method: "PATCH",
            body: JSON.stringify(updates),
          });
          await get().fetchAutomationRules();
        } catch (error) {
          set({ error: (error as Error).message });
        }
      },

      deleteAutomationRule: async (id) => {
        try {
          await fetchAPI(`/api/automation/rules/${id}`, {
            method: "DELETE",
          });
          await get().fetchAutomationRules();
        } catch (error) {
          set({ error: (error as Error).message });
        }
      },

      toggleAutomationRule: async (id, isActive) => {
        try {
          await fetchAPI(`/api/automation/rules/${id}/toggle`, {
            method: "PATCH",
            body: JSON.stringify({ isActive }),
          });
          await get().fetchAutomationRules();
        } catch (error) {
          set({ error: (error as Error).message });
        }
      },

      setPaperBalance: async (currency, amount) => {
        try {
          await fetchAPI("/api/paper/balance", {
            method: "POST",
            body: JSON.stringify({ currency, amount }),
          });
          await get().fetchBalance();
        } catch (error) {
          set({ error: (error as Error).message });
        }
      },

      resetPaperAccount: async (startBalance) => {
        try {
          await fetchAPI("/api/paper/reset", {
            method: "POST",
            body: JSON.stringify({ startBalance }),
          });
          await get().fetchBalance();
        } catch (error) {
          set({ error: (error as Error).message });
        }
      },

      // ===========================
      // Logs Actions
      // ===========================

      fetchLogs: async (limit = 100, level) => {
        set((state) => ({ isLoading: { ...state.isLoading, logs: true } }));
        try {
          const url = level 
            ? `/api/logs/?limit=${limit}&level=${level}` 
            : `/api/logs/?limit=${limit}`;
          const data = await fetchAPI<LogEntry[]>(url);
          if (data) {
            set({ logs: data });
          }
        } catch (error) {
          set({ error: (error as Error).message });
        } finally {
          set((state) => ({ isLoading: { ...state.isLoading, logs: false } }));
        }
      },

      clearLogs: async (days = 0) => {
        try {
          await fetchAPI(`/api/logs/clear?days=${days}`, {
            method: "DELETE",
          });
          await get().fetchLogs();
        } catch (error) {
          set({ error: (error as Error).message });
        }
      },

      // ===========================
      // Backtest Actions
      // ===========================

      runBacktest: async (ruleId, days, balance, exitRuleId) => {
        try {
          const results = await fetchAPI<any>("/api/backtest/run", {
            method: "POST",
            body: JSON.stringify({
              rule_id: ruleId,
              exit_rule_id: exitRuleId || null,
              start_days_ago: days,
              initial_balance: balance,
            }),
          });
          return results;
        } catch (error) {
          const message = (error as Error).message;
          set({ error: message });
          return { error: message };
        }
      },

      downloadBacktestData: async (symbol, timeframe, days) => {
        try {
          await fetchAPI("/api/backtest/download", {
            method: "POST",
            body: JSON.stringify({
              symbol,
              timeframe,
              days,
            }),
          });
        } catch (error) {
          set({ error: (error as Error).message });
        }
      },

      runTuning: async (options) => {
        try {
          const payload = {
            auto_apply: options?.autoApply ?? true,
            all_symbols: options?.allSymbols ?? true,
            skip_download: options?.skipDownload ?? false,
            fast: options?.fast ?? false,
            focus_symbols: options?.focusSymbols ?? null,
          };
          const result = await fetchAPI<TuningStatus>("/api/tuning/run", {
            method: "POST",
            body: JSON.stringify(payload),
          });
          return result;
        } catch (error) {
          set({ error: (error as Error).message });
          return null;
        }
      },

      fetchTuningStatus: async () => {
        try {
          const result = await fetchAPI<TuningStatus>("/api/tuning/status");
          return result;
        } catch (error) {
          set({ error: (error as Error).message });
          return null;
        }
      },

      // ===========================
      // History Actions
      // ===========================

      loadHistory: () => {
        try {
          const trades = localStorage.getItem("trade_history");
          const scans = localStorage.getItem("scan_history");

          set({
            tradeHistory: trades ? JSON.parse(trades) : [],
            scanHistory: scans
              ? JSON.parse(scans).map((scan: ScanResult) => {
                  if (typeof scan.timestamp === "string") {
                    const parsed = Date.parse(scan.timestamp);
                    return {
                      ...scan,
                      timestamp: Number.isNaN(parsed)
                        ? parseInt(scan.timestamp, 10)
                        : parsed,
                    };
                  }
                  return scan;
                })
              : [],
          });
        } catch (err) {
          console.error("Failed to load history:", err);
        }
      },

      clearTradeHistory: () => {
        localStorage.removeItem("trade_history");
        set({ tradeHistory: [] });
      },

      clearScanHistory: () => {
        localStorage.removeItem("scan_history");
        set({ scanHistory: [] });
      },

      // ===========================
      // Utility Actions
      // ===========================

      refreshAll: async () => {
        const { fetchTicker, fetchScan, fetchPortfolio, fetchPositions, fetchMetrics } =
          get();

        try {
          await Promise.all([
            fetchTicker(),
            fetchScan(),
            fetchPortfolio(),
            fetchPositions(),
            fetchMetrics(),
          ]);
        } catch (error) {
          console.error("Error refreshing all data:", error);
        }
      },

      reset: () => {
        set({
          isConnected: false,
          lastUpdate: Date.now(),
          error: null,
          ticker: null,
          scanResult: null,
          historicalData: null,
          portfolio: null,
          balance: null,
          positions: [],
          portfolioHistory: [],
          metrics: null,
          riskExposure: null,
          recentTrades: [],
          allTrades: [],
          isLoading: defaultLoadingState,
        });
      },
    }),
    {
      name: "nobibot-storage",
      // Only persist user settings, not data
      partialize: (state) => ({
        selectedSymbol: state.selectedSymbol,
        selectedTimeframe: state.selectedTimeframe,
        settings: state.settings,
        riskLimits: state.riskLimits,
      }),
    }
  )
);

// ===========================
// Auto-refresh Hook
// ===========================

/**
 * Hook to enable auto-refresh of data
 * Usage: useAutoRefresh(10000) // refresh every 10 seconds
 */
export function useAutoRefresh(interval = 10000) {
  const { refreshAll, settings } = useTradingStore();

  useEffect(() => {
    if (typeof window === "undefined" || !settings.enableAutoRefresh) {
      return;
    }

    const timer = setInterval(() => {
      refreshAll();
    }, interval);

    return () => clearInterval(timer);
  }, [refreshAll, settings.enableAutoRefresh, interval]);
}
