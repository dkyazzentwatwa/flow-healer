import type { Portfolio } from "./types";

export type PortfolioSummaryTone = "neutral" | "positive" | "negative";

export interface PortfolioSummaryStat {
  label: string;
  value: string;
  tone: PortfolioSummaryTone;
  numericValue: number | null;
  icon: "wallet" | "cash" | "unrealized" | "realized";
}

type PortfolioSummaryInput = Partial<Portfolio> | null | undefined;

const EMPTY_VALUE = "—";

function toFiniteNumber(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return value;
}

function formatCurrency(value: unknown): string {
  const amount = toFiniteNumber(value);
  if (amount === null) {
    return EMPTY_VALUE;
  }

  return amount.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function getTone(value: unknown): PortfolioSummaryTone {
  const amount = toFiniteNumber(value);
  if (amount === null) {
    return "neutral";
  }
  return amount >= 0 ? "positive" : "negative";
}

export function buildPortfolioSummaryStats(
  portfolio?: PortfolioSummaryInput
): PortfolioSummaryStat[] {
  return [
    {
      label: "Total Portfolio Value",
      value: formatCurrency(portfolio?.totalValue),
      tone: "neutral",
      numericValue: toFiniteNumber(portfolio?.totalValue),
      icon: "wallet",
    },
    {
      label: "Cash Balance",
      value: formatCurrency(portfolio?.cash),
      tone: "neutral",
      numericValue: toFiniteNumber(portfolio?.cash),
      icon: "cash",
    },
    {
      label: "Unrealized P&L",
      value: formatCurrency(portfolio?.unrealizedPnl),
      tone: getTone(portfolio?.unrealizedPnl),
      numericValue: toFiniteNumber(portfolio?.unrealizedPnl),
      icon: "unrealized",
    },
    {
      label: "Realized P&L Today",
      value: formatCurrency(portfolio?.realizedPnl),
      tone: getTone(portfolio?.realizedPnl),
      numericValue: toFiniteNumber(portfolio?.realizedPnl),
      icon: "realized",
    },
  ];
}
