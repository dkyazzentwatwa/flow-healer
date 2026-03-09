import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BillingPage from "@/components/dashboard/BillingPage";

const mockUseQuery = vi.fn();
const mockUseActiveBusiness = vi.fn();

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
}));

vi.mock("@/contexts/BusinessContext", () => ({
  useActiveBusiness: () => mockUseActiveBusiness(),
}));

vi.mock("@/integrations/supabase/client", () => ({
  supabase: {
    functions: { invoke: vi.fn() },
    from: vi.fn(),
  },
}));

vi.mock("@/hooks/use-toast", () => ({
  toast: vi.fn(),
}));

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  BarChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  CartesianGrid: () => null,
}));

function makeUsageRecords(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    id: `usage-${index}`,
    type: "chat",
    recorded_at: "2026-03-01T12:00:00.000Z",
  }));
}

function renderBillingPage(chatCount: number) {
  const subscription = {
    plan: "free",
    status: "active",
    current_period_start: "2026-03-01T00:00:00.000Z",
    current_period_end: "2026-03-31T23:59:59.000Z",
  };

  mockUseQuery.mockImplementation(({ queryKey }: { queryKey: unknown[] }) => {
    switch (queryKey[0]) {
      case "stripe-subscription":
        return { data: { subscribed: false, plan: "free" } };
      case "subscription":
        return { data: subscription, isLoading: false };
      case "usage":
        return { data: makeUsageRecords(chatCount), isLoading: false };
      default:
        return { data: undefined, isLoading: false };
    }
  });

  return render(
    <MemoryRouter initialEntries={["/dashboard/billing"]}>
      <BillingPage />
    </MemoryRouter>,
  );
}

describe("BillingPage", () => {
  beforeEach(() => {
    mockUseQuery.mockReset();
    mockUseActiveBusiness.mockReturnValue({
      activeBusiness: { id: "business-1", name: "Prosper Co" },
    });
  });

  it("keeps bounded usage meters pinned at zero instead of rendering a negative width", () => {
    renderBillingPage(-5);

    expect(screen.getByTestId("chat-usage-meter")).toHaveStyle({ width: "0%" });
  });

  it("caps bounded usage meters at one hundred percent when usage exceeds the plan limit", () => {
    renderBillingPage(55);

    expect(screen.getByTestId("chat-usage-meter")).toHaveStyle({ width: "100%" });
  });
});
