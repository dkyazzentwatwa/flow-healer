/**
 * Utility Functions for NobiBot Dashboard
 * Formatting, parsing, and helper functions used throughout the app
 */

import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind CSS classes with clsx
 * Handles conditional classes and removes conflicts
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a number with specified decimal places
 * @param value - Number or string to format
 * @param decimals - Number of decimal places (default: 2)
 * @returns Formatted string with commas
 */
export function formatNumber(value: number | string | null | undefined, decimals = 2): string {
  if (value === null || value === undefined) {
    return "—";
  }

  // Convert string to number if needed
  const numValue = typeof value === "string" ? parseFloat(value) : value;

  if (isNaN(numValue)) {
    return "—";
  }

  return numValue.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/**
 * Format a percentage with + sign for positive values
 * @param value - Decimal value (0.05 = 5%)
 * @param decimals - Number of decimal places (default: 2)
 * @returns Formatted percentage string with + or -
 */
export function formatPercent(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || isNaN(value)) {
    return "—";
  }

  const formatted = (value * 100).toFixed(decimals);
  return value >= 0 ? `+${formatted}%` : `${formatted}%`;
}

/**
 * Format a currency value with $ symbol
 * @param value - Currency amount
 * @param decimals - Number of decimal places (default: 2)
 * @returns Formatted currency string
 */
export function formatCurrency(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || isNaN(value)) {
    return "—";
  }

  return `$${formatNumber(value, decimals)}`;
}

/**
 * Format a Unix timestamp to readable date/time
 * @param timestamp - Unix timestamp in seconds or milliseconds (number or string)
 * @param includeTime - Whether to include time (default: true)
 * @returns Formatted date string
 */
export function formatTimestamp(timestamp: number | string, includeTime = true): string {
  if (!timestamp) return "—";

  // Convert string to number if needed
  const ts = typeof timestamp === "string" ? parseInt(timestamp, 10) : timestamp;

  // Convert to milliseconds if needed
  const ms = ts < 10000000000 ? ts * 1000 : ts;
  const date = new Date(ms);

  if (includeTime) {
    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * Format a date string to readable format
 * @param dateStr - ISO date string
 * @returns Formatted date string
 */
export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";

  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return "—";
  }
}

/**
 * Format a duration in seconds to human-readable string
 * @param seconds - Duration in seconds
 * @returns Formatted duration (e.g., "2d 3h", "45m", "12s")
 */
export function formatDuration(seconds: number): string {
  if (!seconds || isNaN(seconds)) return "—";

  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (days > 0) {
    return `${days}d ${hours}h`;
  } else if (hours > 0) {
    return `${hours}h ${minutes}m`;
  } else if (minutes > 0) {
    return `${minutes}m`;
  } else {
    return `${secs}s`;
  }
}

/**
 * Convert snake_case to camelCase
 * @param obj - Object with snake_case keys
 * @returns Object with camelCase keys
 */
export function snakeToCamel<T = any>(obj: any): T {
  if (obj === null || obj === undefined) return obj;
  if (typeof obj !== "object") return obj;
  if (Array.isArray(obj)) return obj.map(snakeToCamel) as any;

  const result: any = {};
  for (const key in obj) {
    const camelKey = key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
    result[camelKey] = snakeToCamel(obj[key]);
  }
  return result;
}

/**
 * Convert camelCase to snake_case
 * @param obj - Object with camelCase keys
 * @returns Object with snake_case keys
 */
export function camelToSnake<T = any>(obj: any): T {
  if (obj === null || obj === undefined) return obj;
  if (typeof obj !== "object") return obj;
  if (Array.isArray(obj)) return obj.map(camelToSnake) as any;

  const result: any = {};
  for (const key in obj) {
    const snakeKey = key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
    result[snakeKey] = camelToSnake(obj[key]);
  }
  return result;
}

/**
 * Calculate color class based on value
 * @param value - Numeric value (positive/negative)
 * @returns Tailwind color class
 */
export function getColorClass(value: number | null | undefined): string {
  if (value === null || value === undefined || isNaN(value)) {
    return "text-zinc-400";
  }
  return value >= 0 ? "text-green-400" : "text-red-400";
}

/**
 * Debounce a function
 * @param func - Function to debounce
 * @param wait - Wait time in milliseconds
 * @returns Debounced function
 */
export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout;

  return function executedFunction(...args: Parameters<T>) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };

    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

/**
 * Sleep for specified milliseconds
 * @param ms - Milliseconds to sleep
 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Get relative time string (e.g., "2 hours ago")
 * @param timestamp - Unix timestamp
 * @returns Relative time string
 */
export function getRelativeTime(timestamp: number): string {
  if (!timestamp) return "—";

  const ms = timestamp < 10000000000 ? timestamp * 1000 : timestamp;
  const seconds = Math.floor((Date.now() - ms) / 1000);

  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

/**
 * Get price change color class
 * @param change - Price change value
 * @returns Tailwind color class
 */
export function getPriceColorClass(change: number): string {
  if (change > 0) return "text-green-400";
  if (change < 0) return "text-red-400";
  return "text-zinc-400";
}

/**
 * Get signal color class
 * @param signal - Signal type (buy, sell, bullish, bearish, etc.)
 * @returns Tailwind color class
 */
export function getSignalColorClass(signal?: string): string {
  if (!signal) return "text-zinc-400";
  const normalized = signal.toLowerCase();
  if (normalized.includes("buy") || normalized === "bullish") return "text-green-400";
  if (normalized.includes("sell") || normalized === "bearish") return "text-red-400";
  return "text-yellow-400";
}

/**
 * Common trading symbols
 */
export const COMMON_SYMBOLS = [
  "BTC/USDT",
  "ETH/USDT",
  "BNB/USDT",
  "SOL/USDT",
  "XRP/USDT",
  "ADA/USDT",
  "DOGE/USDT",
  "MATIC/USDT",
  "DOT/USDT",
  "AVAX/USDT",
];

/**
 * Common timeframes
 */
export const TIMEFRAMES = [
  { value: "1m", label: "1 Minute" },
  { value: "5m", label: "5 Minutes" },
  { value: "15m", label: "15 Minutes" },
  { value: "1h", label: "1 Hour" },
  { value: "4h", label: "4 Hours" },
  { value: "1d", label: "1 Day" },
];
