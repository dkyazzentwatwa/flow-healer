import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

import PaywallGate from "@/components/dashboard/PaywallGate";

const mockUseQuery = vi.fn();
const mockUseActiveBusiness = vi.fn();

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
}));

vi.mock("@/contexts/BusinessContext", () => ({
  useActiveBusiness: () => mockUseActiveBusiness(),
}));

vi.mock("@/integrations/supabase/client", () => ({
  supabase: {},
}));

describe("PaywallGate", () => {
  beforeEach(() => {
    mockUseActiveBusiness.mockReturnValue({
      activeBusiness: { id: "business-1", name: "Prosper Co" },
    });
  });

  it("renders starter plan limits from plan metadata when pro access is required", () => {
    mockUseQuery.mockReturnValue({
      data: { plan: "free", status: "active" },
    });

    render(
      <MemoryRouter>
        <PaywallGate requiredPlan="pro">
          <div>Analytics content</div>
        </PaywallGate>
      </MemoryRouter>,
    );

    expect(screen.getByText("Starter plan")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Upgrade to Pro to unlock Analytics" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "Your Starter plan includes 50 chats / month, 10 leads / month, 1 bot. Upgrade to Pro for Unlimited chats / month, Unlimited leads / month, 5 bots and analytics insights.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Analytics content")).toBeInTheDocument();
  });

  it("renders pro plan limits when agency access is required", () => {
    mockUseQuery.mockReturnValue({
      data: { plan: "pro", status: "active" },
    });

    render(
      <MemoryRouter>
        <PaywallGate requiredPlan="agency">
          <div>Agency analytics</div>
        </PaywallGate>
      </MemoryRouter>,
    );

    expect(screen.getByText("Pro plan")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Upgrade to Agency to unlock Analytics" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "Your Pro plan includes Unlimited chats / month, Unlimited leads / month, 5 bots. Upgrade to Agency for Unlimited chats / month, Unlimited leads / month, Unlimited bots and analytics insights.",
      ),
    ).toBeInTheDocument();
  });

  it("renders children without the gate when the current plan already has access", () => {
    mockUseQuery.mockReturnValue({
      data: { plan: "agency", status: "active" },
    });

    render(
      <MemoryRouter>
        <PaywallGate requiredPlan="pro">
          <div>Unlocked analytics</div>
        </PaywallGate>
      </MemoryRouter>,
    );

    expect(screen.getByText("Unlocked analytics")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Upgrade to/i })).not.toBeInTheDocument();
  });
});
