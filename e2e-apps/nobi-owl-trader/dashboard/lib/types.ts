/**
 * TypeScript Type Definitions for NobiBot Portfolio & P&L Analytics
 * Complete type safety for all data models used across the dashboard
 */

// ===========================
// Market Data Types
// ===========================

/**
 * Real-time ticker data for a trading pair
 */
export interface Ticker {
  symbol: string;
  last: number;
  bid: number;
  ask: number;
  high: number;
  low: number;
  volume: number;
  change: number;
  changePercent: number;
  timestamp: number;
}

/**
 * Technical indicator result
 */
export interface Indicator {
  name: string;
  value: number | string;
  score: number;
  signal: string;
  details?: Record<string, unknown>;
}

/**
 * Scan result with technical analysis
 */
export interface ScanResult {
  symbol: string;
  exchange: string;
  timeframe: string;
  timestamp: number | string;
  scoreTotal: number;
  tradeSignal: string;
  indicators: Indicator[];
  ohlcv: {
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  };
}

// ===========================
// Trading Types
// ===========================

/**
 * Trade execution record
 */
export interface Trade {
  id: string;
  symbol: string;
  side: "buy" | "sell";
  amount: number;
  price: number;
  total: number;
  fee: number;
  feeCurrency?: string;
  timestamp: number;
  status: "open" | "closed" | "cancelled";
  paper: boolean;
  strategy?: string;
  notes?: string;
  stopPrice?: number;
  targetPrice?: number;
  isTrailing?: boolean;
  highestPrice?: number;
  lowestPrice?: number;
}

/**
 * Order response from trading API
 */
export interface OrderResponse {
  id: string;
  symbol: string;
  side: string;
  type: string;
  amount: number;
  price?: number;
  status: string;
  paperTrade?: boolean;
}

/**
 * Current position held
 */
export interface Position {
  symbol: string;
  quantity: number;
  avgCost: number;
  currentPrice: number;
  marketValue: number;
  unrealizedPnl: number;
  unrealizedPnlPercent: number;
  realizedPnl: number;
  totalPnl: number;
  totalPnlPercent: number;
  firstBuyDate: number;
  lastBuyDate: number;
  trades: Trade[];
}

// ===========================
// Portfolio Types
// ===========================

/**
 * Portfolio summary and balance information
 */
export interface Portfolio {
  totalValue: number;
  cash: number;
  positions: number;
  totalCost: number;
  unrealizedPnl: number;
  unrealizedPnlPercent: number;
  realizedPnl: number;
  totalPnl: number;
  totalPnlPercent: number;
  timestamp: number;
}

/**
 * Performance metrics over time period
 */
export interface PerformanceMetrics {
  totalReturn: number;
  totalReturnPercent: number;
  dayReturn: number;
  dayReturnPercent: number;
  weekReturn: number;
  weekReturnPercent: number;
  monthReturn: number;
  monthReturnPercent: number;
  winRate: number;
  profitFactor: number;
  sharpeRatio: number;
  maxDrawdown: number;
  maxDrawdownPercent: number;
  avgWin: number;
  avgLoss: number;
  totalTrades: number;
  winningTrades: number;
  losingTrades: number;
  largestWin: number;
  largestLoss: number;
  avgHoldingPeriod: number;
}

/**
 * Historical portfolio snapshot
 */
export interface PortfolioSnapshot {
  timestamp: number;
  totalValue: number;
  cash: number;
  positionsValue: number;
  totalPnl: number;
  totalPnlPercent: number;
  dayChange: number;
  dayChangePercent: number;
}

/**
 * Exchange/Paper balance snapshot
 */
export interface Balance {
  total: Record<string, number>;
  free: Record<string, number>;
  used: Record<string, number>;
}

// ===========================
// Tuning Types
// ===========================

export interface TuningStatus {
  running: boolean;
  pid?: number | null;
  logTail?: string;
  logFile?: string;
  checkedAt?: string;
}

// ===========================
// Risk Management Types
// ===========================

/**
 * Risk limits and thresholds
 */
export interface RiskLimits {
  maxDailyLoss: number;
  maxDrawdownPercent: number;
  maxPositionSizePercent: number;
  maxExposurePercent: number;
  stopLossPercent: number;
  takeProfitPercent: number;
  trailingStopPercent: number;
}

/**
 * Current risk exposure
 */
export interface RiskExposure {
  canTrade: boolean;
  reason: string;
  warning?: string | null;
  todayPnl: number;
  portfolioValue: number;
  totalExposure: number;
  exposurePercent: number;
  peakEquity: number;
  drawdown: number;
  drawdownPercent: number;
}

// ===========================
// Settings & User Prefs
// ===========================

/**
 * User settings and preferences
 */
export interface UserSettings {
  theme: "dark" | "light";
  currency: "USD" | "BTC" | "ETH";
  defaultSymbol: string;
  refreshInterval: number;
  enableNotifications: boolean;
  enableAutoRefresh: boolean;
  chartType: "candlestick" | "line" | "bar";
  timeframe: "1m" | "5m" | "15m" | "1h" | "4h" | "1d";
  apiUrl: string;
  riskLimits: RiskLimits;
}

// ===========================
// Automation Types
// ===========================

export interface AutomationRule {
  id: string;
  name: string;
  symbol: string;
  timeframe: string;
  side: "buy" | "sell";
  triggerType: "signal" | "price";
  signalType: string;
  amount: number;
  amountType: "fixed" | "percent";
  stopLossPct?: number;
  takeProfitPct?: number;
  trailingStopPct?: number;
  onlyIfInPosition?: boolean;
  reduceOnly?: boolean;
  minProfitPct?: number;
  breakEvenAfterPct?: number;
  maxHoldBars?: number;
  minScore?: number;
  isActive: boolean;
  lastTriggered: number;
  cooldownMinutes: number;
  conditions?: string;
}

export interface LogEntry {
  id: number;
  timestamp: number;
  level: string;
  message: string;
  ruleId?: string;
  symbol?: string;
  details?: string;
}

// ===========================
// API Response Types
// ===========================

/**
 * Generic API response wrapper
 */
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  timestamp: number;
}

/**
 * WebSocket message types
 */
export type WsMessage =
  | { type: "ticker"; data: Ticker }
  | { type: "scan"; data: ScanResult }
  | { type: "trade"; data: Trade }
  | { type: "portfolio"; data: Portfolio }
  | { type: "position"; data: Position }
  | { type: "error"; error: string };

// ===========================
// Chart Data Types
// ===========================

/**
 * OHLCV candlestick data
 */
export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/**
 * Historical data response
 */
export interface HistoricalData {
  symbol: string;
  interval: string;
  candles: Candle[];
}
